"""post 业务逻辑：发帖（悬赏同事务扣分）/详情/编辑（15 分钟窗口）/软删级联。"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BizError, ErrCode
from app.core.sensitive import contains_sensitive
from app.models import Answer, Comment, Favorite, LikeRecord, Post, PostTag, Tag, User
from app.modules.credit import service as credit_service
from app.modules.notify import service as notify_service
from app.modules.credit.sources import CreditSource
from app.modules.post.schemas import MyAnswerItem, MyCommentItem, MyLikeItem, PostCard, PostDetail, TagItem

EDIT_WINDOW_MINUTES = 15


def _validate_common(db: Session, title: str, content: str, tag_ids: list[int]) -> list[Tag]:
    """标题/正文敏感词 + 标签数量与有效性校验，返回 Tag 对象列表。"""
    if contains_sensitive(title) or contains_sensitive(content):
        raise BizError(ErrCode.SENSITIVE_WORD, "标题或内容含违禁词")
    if len(tag_ids) < 1 or len(tag_ids) > settings.TAG_MAX_PER_POST:
        raise BizError(ErrCode.BAD_REQUEST, f"标签数量须为 1-{settings.TAG_MAX_PER_POST} 个")
    tags = (
        db.execute(select(Tag).where(Tag.id.in_(tag_ids), Tag.enabled == 1)).scalars().all()
    )
    if len(tags) != len(set(tag_ids)):
        raise BizError(ErrCode.BAD_REQUEST, "存在无效标签")
    return list(tags)


def _sync_tags(db: Session, post_id: int, tags: list[Tag]) -> None:
    db.execute(PostTag.__table__.delete().where(PostTag.post_id == post_id))
    for t in tags:
        db.add(PostTag(post_id=post_id, tag_id=t.id))


def _tags_of(db: Session, post_id: int) -> list[TagItem]:
    rows = db.execute(
        select(Tag).join(PostTag, PostTag.tag_id == Tag.id).where(PostTag.post_id == post_id)
    ).scalars().all()
    return [TagItem(id=t.id, name=t.name) for t in rows]


def _no_answer_days(post: Post) -> int | None:
    """待解决帖超 NO_ANSWER_MARK_DAYS 且无新回答 → 距最近回答（无回答则发帖）天数，否则 None。"""
    if post.status != 0:
        return None
    base = post.last_answer_at or post.created_at
    days = (datetime.now() - base).days
    return days if days > settings.NO_ANSWER_MARK_DAYS else None


# ---- 相似问答推荐（V1.1）----
# 冷启动方案：标题字符 bigram Jaccard + 标签重合加权 + 已解决/热度加成，全内存计算。
# TODO 量大后切 MySQL 全文索引或 LLM 网关 similar_qa 场景（契约已就绪 app/gateway/contracts.py）。

SIMILAR_MIN_SCORE = 0.2  # 低于该分数不推荐（避免无意义结果）
_TAG_BONUS_PER = 0.15    # 每个重合标签加分
_TAG_BONUS_MAX = 0.3
_SOLVED_BONUS = 0.1      # 已解决帖（有采纳答案）加成
_ANSWER_BONUS_PER = 0.02  # 每个回答小幅加成
_ANSWER_BONUS_MAX = 0.06


def _bigrams(text: str) -> set[str]:
    """中文友好：去空白标点后取相邻字符二元组（"依赖注入" → {依赖,赖注,注入}）。"""
    cleaned = "".join(ch for ch in (text or "").lower() if ch.isalnum())
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)} if len(cleaned) > 1 else {cleaned} if cleaned else set()


def _similar_score(
    query_bigrams: set[str], post: Post, post_tag_ids: set[int], query_tag_ids: set[int]
) -> float:
    """标题 bigram Jaccard + 标签/状态/热度加权。"""
    target = _bigrams(post.title)
    if not query_bigrams or not target:
        return 0.0
    union = query_bigrams | target
    sim = len(query_bigrams & target) / len(union) if union else 0.0
    tag_bonus = min(_TAG_BONUS_PER * len(post_tag_ids & query_tag_ids), _TAG_BONUS_MAX)
    solved_bonus = _SOLVED_BONUS if post.status == 1 else 0.0
    answer_bonus = min(post.answer_count * _ANSWER_BONUS_PER, _ANSWER_BONUS_MAX)
    return sim + tag_bonus + solved_bonus + answer_bonus


def similar_posts(
    db: Session,
    q: str,
    tag_ids: list[int],
    exclude_id: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """相似问答推荐：返回带 score 的 PostCard 列表（降序，低于阈值过滤）。

    用途：发帖页防重复提问（输入标题实时提示）+ 帖子详情页"相关问题"。
    """
    query_bigrams = _bigrams(q)
    if not query_bigrams:
        return []
    query_tags = set(tag_ids or [])
    posts = (
        db.execute(
            select(Post).where(Post.deleted_at.is_(None)).order_by(Post.created_at.desc()).limit(1000)
        )
        .scalars()
        .all()
    )
    scored: list[tuple[float, Post]] = []
    for p in posts:
        if p.id == exclude_id:
            continue
        p_tags = {
            t.id
            for t in db.execute(
                select(Tag).join(PostTag, PostTag.tag_id == Tag.id).where(PostTag.post_id == p.id)
            ).scalars()
        }
        score = _similar_score(query_bigrams, p, p_tags, query_tags)
        if score >= SIMILAR_MIN_SCORE:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {**_card(db, p), "similar_score": round(s, 3)} for s, p in scored[:limit]
    ]


def _card(db: Session, post: Post, author: User | None = None) -> dict:
    if author is None:
        author = db.get(User, post.author_id)
    return PostCard(
        id=post.id,
        title=post.title,
        summary=(post.ai_summary or (post.content or "")[:100])[:100],
        author_id=post.author_id,
        author_nickname=author.nickname if author else "已注销",
        status=post.status,
        reward=post.reward,
        answer_count=post.answer_count,
        like_count=post.like_count,
        view_count=post.view_count,
        tags=_tags_of(db, post.id),
        is_rewarded=post.reward > 0,
        no_answer_days=_no_answer_days(post),
        is_ai_summary=bool(post.ai_summary),
        created_at=post.created_at,
    ).model_dump()


def detail_dict(
    db: Session, post: Post, viewer: User | None, author: User | None = None
) -> dict:
    """PostDetail：附当前用户点赞/收藏态。"""
    data = _card(db, post, author)
    data["content"] = post.content or ""
    data["images"] = post.images or []
    data["edited"] = post.updated_at is not None and post.updated_at > post.created_at
    data["ai_summary"] = post.ai_summary
    data["ai_answer"] = post.ai_answer  # V1.3：AI 参考回答（未生成时 None）
    if viewer is not None:
        data["is_liked"] = (
            db.execute(
                select(LikeRecord).where(
                    LikeRecord.user_id == viewer.id,
                    LikeRecord.target_type == 1,
                    LikeRecord.target_id == post.id,
                )
            ).scalar_one_or_none()
            is not None
        )
        data["is_favorite"] = (
            db.execute(
                select(Favorite).where(
                    Favorite.user_id == viewer.id,
                    Favorite.target_type == 1,
                    Favorite.target_id == post.id,
                )
            ).scalar_one_or_none()
            is not None
        )
    else:
        data["is_liked"] = False
        data["is_favorite"] = False
    return data


def get_post_or_404(db: Session, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None or post.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "帖子不存在或已删除")
    return post


def create_post(
    db: Session, user: User, title: str, content: str, images: list[str], tag_ids: list[int], reward: int
) -> dict:
    """发帖：悬赏扣分与发帖同事务，余额不足整体回滚（40902 响应含余额）。"""
    if reward not in (0, *settings.REWARD_TIERS):
        raise BizError(ErrCode.BAD_REQUEST, f"悬赏档位须为 {settings.REWARD_TIERS} 或 0")
    tags = _validate_common(db, title, content, tag_ids)

    post = Post(
        author_id=user.id,
        title=title,
        content=content,
        images=images or None,
        reward=reward,
    )
    db.add(post)
    db.flush()
    for t in tags:
        db.add(PostTag(post_id=post.id, tag_id=t.id))
    if reward > 0:
        try:
            credit_service.deduct(
                db, user.id, CreditSource.REWARD, reward,
                ref_type=1, ref_id=post.id, note=f"悬赏支出（帖子 {post.id}）",
            )
        except BizError as e:
            db.rollback()
            raise BizError(e.code, e.msg) from e
    db.commit()
    return detail_dict(db, post, user, author=user)


def get_detail(db: Session, post_id: int, viewer: User | None) -> dict:
    """帖子详情：view_count +1（读侧计数，直接更新）。"""
    post = get_post_or_404(db, post_id)
    post.view_count += 1
    db.commit()
    return detail_dict(db, post, viewer)


def update_post(
    db: Session, user: User, post_id: int, title: str, content: str, images: list[str], tag_ids: list[int]
) -> dict:
    """编辑帖子：仅帖主（40301）+ 15 分钟窗口（40001）+ reward 不可改。"""
    post = get_post_or_404(db, post_id)
    if post.author_id != user.id:
        raise BizError(ErrCode.FORBIDDEN, "仅帖子作者可编辑")
    if post.created_at + timedelta(minutes=EDIT_WINDOW_MINUTES) < datetime.now():
        raise BizError(ErrCode.BAD_REQUEST, "发布超过 15 分钟，不可编辑")
    tags = _validate_common(db, title, content, tag_ids)
    post.title = title
    post.content = content
    post.images = images or None
    post.ai_answer = None  # V1.3：内容已变 → AI 参考回答缓存作废（下次触发重新生成）
    post.ai_answer_at = None
    _sync_tags(db, post.id, tags)
    db.commit()
    return detail_dict(db, post, user, author=user)


def delete_post(db: Session, user: User, post_id: int) -> None:
    """软删帖子：悬赏不退回（PRD 落定）。级联隐藏由查询侧 deleted_at 过滤实现。"""
    post = get_post_or_404(db, post_id)
    if post.author_id != user.id:
        raise BizError(ErrCode.FORBIDDEN, "仅帖子作者可删除")
    post.deleted_at = datetime.now()
    notify_service.invalidate(db, 1, post_id)  # 指向该帖的通知（被回答/被评论/被点赞）失效
    db.commit()


def my_posts(db: Session, user_id: int, status: int | None, offset: int, limit: int) -> dict:
    """我的帖子列表：可选状态过滤，倒序。"""
    q = select(Post).where(Post.author_id == user_id, Post.deleted_at.is_(None))
    if status is not None:
        q = q.where(Post.status == status)
    total = len(db.execute(q).scalars().all())
    rows = (
        db.execute(q.order_by(Post.id.desc()).offset(offset).limit(limit)).scalars().all()
    )
    return {"total": total, "items": [_card(db, p) for p in rows]}


# ---- 个人中心（V1.12）：我的回答/评论/点赞 + 他人公开内容 + 统计 ----


def _paginate(q, db: Session, offset: int, limit: int):
    """通用计数+分页（与 my_posts 同口径）。"""
    total = len(db.execute(q).scalars().all())
    rows = db.execute(q.offset(offset).limit(limit)).scalars().all()
    return total, rows


def _answer_items(db: Session, answers: list[Answer]) -> list[MyAnswerItem]:
    """Answer → MyAnswerItem：批量查所属帖（未删），已删帖 post_title=None。"""
    post_ids = {a.post_id for a in answers}
    posts = (
        db.execute(select(Post).where(Post.id.in_(post_ids), Post.deleted_at.is_(None))).scalars().all()
        if post_ids
        else []
    )
    pmap = {p.id: p for p in posts}
    return [
        MyAnswerItem(
            id=a.id,
            post_id=a.post_id,
            post_title=pmap[a.post_id].title if a.post_id in pmap else None,
            post_status=pmap[a.post_id].status if a.post_id in pmap else None,
            content=a.content,
            is_accepted=bool(a.is_accepted),
            is_best=bool(a.is_best),
            like_count=a.like_count,
            created_at=a.created_at,
        )
        for a in answers
    ]


def my_answers(db: Session, user_id: int, offset: int, limit: int) -> dict:
    """我的回答列表：倒序，含所属帖标题与采纳/最佳/赞数。"""
    q = select(Answer).where(Answer.author_id == user_id, Answer.deleted_at.is_(None))
    total, rows = _paginate(q.order_by(Answer.id.desc()), db, offset, limit)
    return {"total": total, "items": [i.model_dump() for i in _answer_items(db, rows)]}


def user_public_answers(db: Session, user_id: int, offset: int, limit: int) -> dict:
    """他人主页：TA 的公开回答（本人也可看，同一份数据）。"""
    return my_answers(db, user_id, offset, limit)


def user_public_posts(db: Session, user_id: int, offset: int, limit: int) -> dict:
    """他人主页：TA 的公开提问。"""
    q = select(Post).where(Post.author_id == user_id, Post.deleted_at.is_(None))
    total, rows = _paginate(q.order_by(Post.id.desc()), db, offset, limit)
    return {"total": total, "items": [_card(db, p) for p in rows]}


def my_comments(db: Session, user_id: int, offset: int, limit: int) -> dict:
    """我的评论列表：倒序；target 解析所属帖（回答评论取其 post_id）。"""
    q = select(Comment).where(Comment.author_id == user_id, Comment.deleted_at.is_(None))
    total, rows = _paginate(q.order_by(Comment.id.desc()), db, offset, limit)

    items: list[MyCommentItem] = []
    for c in rows:
        post_id: int | None = None
        post_title: str | None = None
        if c.target_type == 1:
            p = db.get(Post, c.target_id)
            if p is not None and p.deleted_at is None:
                post_id, post_title = p.id, p.title
        else:
            a = db.get(Answer, c.target_id)
            if a is not None and a.deleted_at is None:
                p = db.get(Post, a.post_id)
                if p is not None and p.deleted_at is None:
                    post_id, post_title = p.id, p.title
        items.append(
            MyCommentItem(
                id=c.id,
                target_type=c.target_type,
                target_id=c.target_id,
                post_id=post_id,
                post_title=post_title,
                content=c.content,
                created_at=c.created_at,
            )
        )
    return {"total": total, "items": [i.model_dump() for i in items]}


def my_likes(db: Session, user_id: int, offset: int, limit: int) -> dict:
    """我的点赞列表：帖/答/评论混合，倒序；目标已删的条目跳过（点赞记录随目标软删清理，
    此处兜底防御）。"""
    q = select(LikeRecord).where(LikeRecord.user_id == user_id)
    total, rows = _paginate(q.order_by(LikeRecord.created_at.desc(), LikeRecord.target_id.desc()), db, offset, limit)

    items: list[MyLikeItem] = []
    for r in rows:
        if r.target_type == 1:
            p = db.get(Post, r.target_id)
            if p is None or p.deleted_at is not None:
                continue
            items.append(
                MyLikeItem(
                    target_type=1, target_id=p.id, post_id=p.id, post_title=p.title,
                    content=p.title, author_nickname=db.get(User, p.author_id).nickname,
                    created_at=r.created_at,
                )
            )
        elif r.target_type == 2:
            a = db.get(Answer, r.target_id)
            if a is None or a.deleted_at is not None:
                continue
            p = db.get(Post, a.post_id)
            items.append(
                MyLikeItem(
                    target_type=2, target_id=a.id,
                    post_id=p.id if p and p.deleted_at is None else None,
                    post_title=p.title if p and p.deleted_at is None else None,
                    content=a.content, author_nickname=db.get(User, a.author_id).nickname,
                    created_at=r.created_at,
                )
            )
        else:
            c = db.get(Comment, r.target_id)
            if c is None or c.deleted_at is not None:
                continue
            # 评论点赞：定位其所属帖供跳转
            post_id = post_title = None
            if c.target_type == 1:
                p = db.get(Post, c.target_id)
                if p is not None and p.deleted_at is None:
                    post_id, post_title = p.id, p.title
            else:
                a = db.get(Answer, c.target_id)
                if a is not None and a.deleted_at is None:
                    p = db.get(Post, a.post_id)
                    if p is not None and p.deleted_at is None:
                        post_id, post_title = p.id, p.title
            items.append(
                MyLikeItem(
                    target_type=3, target_id=c.id, post_id=post_id, post_title=post_title,
                    content=c.content, author_nickname=db.get(User, c.author_id).nickname,
                    created_at=r.created_at,
                )
            )
    return {"total": total, "items": [i.model_dump() for i in items]}


def user_stats(db: Session, user_id: int) -> dict:
    """个人主页统计：提问数/回答数/总获赞数。"""
    post_count = len(
        db.execute(select(Post.id).where(Post.author_id == user_id, Post.deleted_at.is_(None))).all()
    )
    answers = (
        db.execute(select(Answer).where(Answer.author_id == user_id, Answer.deleted_at.is_(None)))
        .scalars().all()
    )
    post_likes = db.execute(
        select(Post.like_count).where(Post.author_id == user_id, Post.deleted_at.is_(None))
    ).scalars().all()
    like_received = sum(post_likes) + sum(a.like_count for a in answers)
    return {
        "post_count": post_count,
        "answer_count": len(answers),
        "like_received": like_received,
    }


# ---- AI 摘要（V1.2 summary 场景）----


def generate_ai_summary_task(post_id: int) -> None:
    """BackgroundTasks 入口：独立会话调用 LLM 生成摘要，任何失败静默降级（保持 None，列表回退正文截断）。

    独立 SessionLocal 而非复用请求会话：后台任务在响应返回后执行，请求级会话已关闭。
    """
    from app.core.database import SessionLocal
    from app.gateway.client import LLMDegradedError, gateway

    with SessionLocal() as db:
        post = db.get(Post, post_id)
        if post is None or post.deleted_at is not None:
            return
        title, content = post.title, post.content or ""
        try:
            out = gateway.invoke("summary", {"title": title, "content": content})
        except LLMDegradedError:
            return  # 降级：ai_summary 保持 None
        post = db.get(Post, post_id)  # 重取防并发过期
        if post is not None and post.deleted_at is None:
            post.ai_summary = (out.get("summary") or "")[:200]
            db.commit()


# ---- AI 参考回答（V1.3 ref_answer 场景）----


def generate_ai_answer(db: Session, user: User, post_id: int) -> dict:
    """用户触发生成 AI 参考回答（同步接口，缓存于 post.ai_answer 一次性付费）。

    产品定位（PRD AI 场景）：兜底参考，非社区回答——不入 answer 表、不计积分、不可被采纳；
    帖子编辑后缓存作废。LLM 不可用返回 40001 提示稍后再试。
    """
    from app.gateway.client import LLMDegradedError, gateway

    post = get_post_or_404(db, post_id)
    if post.ai_answer:  # 命中缓存直接返回
        return {"ai_answer": post.ai_answer, "cached": True}
    try:
        out = gateway.invoke(
            "ref_answer",
            {
                "post_id": post.id,
                "title": post.title,
                "content": (post.content or "")[:2000],
                "tag_names": [t.name for t in _tags_of(db, post.id)],
            },
        )
    except LLMDegradedError:
        raise BizError(ErrCode.BAD_REQUEST, "AI 服务暂不可用，请稍后再试")
    post = db.get(Post, post_id)
    if post is None or post.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "帖子不存在或已删除")
    post.ai_answer = out["answer_text"]
    post.ai_answer_at = datetime.now()
    db.commit()
    return {"ai_answer": out["answer_text"], "cached": False}
