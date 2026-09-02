"""post 业务逻辑：发帖（悬赏同事务扣分）/详情/编辑（15 分钟窗口）/软删级联。"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BizError, ErrCode
from app.core.sensitive import contains_sensitive
from app.models import Favorite, LikeRecord, Post, PostTag, Tag, User
from app.modules.credit import service as credit_service
from app.modules.notify import service as notify_service
from app.modules.credit.sources import CreditSource
from app.modules.post.schemas import PostCard, PostDetail, TagItem

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


def _card(db: Session, post: Post, author: User | None = None) -> dict:
    if author is None:
        author = db.get(User, post.author_id)
    return PostCard(
        id=post.id,
        title=post.title,
        summary=(post.content or "")[:100],
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
