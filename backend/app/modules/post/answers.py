"""回答业务：提交/编辑/删除（40905/40906 已采纳锁）与帖子计数维护。

V1.3：提交/编辑前 AI 质量检测（quality 场景，同步拦截 40913，LLM 不可用时放行）；
提交后异步生成 AI 可靠性评分（reliability 场景，仅展示参考）。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError, ErrCode
from app.core.sensitive import contains_sensitive
from app.models import Answer, Post, User
from app.modules.notify import service as notify_service
from app.modules.post import service as post_service


def _answer_dict(db: Session, a: Answer, viewer: User | None) -> dict:
    author = db.get(User, a.author_id)
    return {
        "id": a.id,
        "post_id": a.post_id,
        "author_id": a.author_id,
        "author_nickname": author.nickname if author else "已注销",
        "content": a.content,
        "is_accepted": bool(a.is_accepted),
        "is_best": bool(a.is_best),
        "like_count": a.like_count,
        "ai_rel_score": a.ai_rel_score,  # V1.3：AI 可靠性（异步生成，未生成时 None）
        "ai_rel_level": a.ai_rel_level,
        "is_liked": False,  # S5 点赞就绪后由列表组装时填充
        "created_at": a.created_at,
    }


def get_answer_or_404(db: Session, answer_id: int) -> Answer:
    a = db.get(Answer, answer_id)
    if a is None or a.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "回答不存在或已删除")
    return a


def _check_quality(db: Session, user: User, content: str) -> None:
    """AI 质量检测（quality 场景）：低质回答拦截 40913；LLM 不可用/超时静默放行（不阻塞社区互动）。"""
    from app.gateway.client import LLMDegradedError, gateway

    history = (
        db.execute(
            select(Answer.content)
            .where(Answer.author_id == user.id, Answer.deleted_at.is_(None))
            .order_by(Answer.id.desc())
            .limit(3)
        )
        .scalars()
        .all()
    )
    try:
        out = gateway.invoke("quality", {"answer_text": content, "author_history": list(history)})
    except LLMDegradedError:
        return  # 降级放行：AI 故障不应让社区停摆
    if out.get("is_low_quality"):
        raise BizError(ErrCode.LOW_QUALITY_ANSWER, f"回答质量过低被拦截：{out.get('reason') or '疑似灌水或与问题无关'}")


def create_answer(db: Session, user: User, post_id: int, content: str) -> dict:
    """提交回答：40904 自问自答/重复回答；40913 AI 低质拦截；维护 answer_count 与 last_answer_at。"""
    post = post_service.get_post_or_404(db, post_id)
    if contains_sensitive(content):
        raise BizError(ErrCode.SENSITIVE_WORD, "内容含违禁词")
    if post.author_id == user.id:
        raise BizError(ErrCode.DUPLICATE_ANSWER, "不能回答自己的提问")
    dup = db.execute(
        select(Answer.id).where(
            Answer.post_id == post_id,
            Answer.author_id == user.id,
            Answer.deleted_at.is_(None),
        )
    ).scalar()
    if dup:
        raise BizError(ErrCode.DUPLICATE_ANSWER, "已回答过该帖子，可编辑原回答")
    _check_quality(db, user, content)  # V1.3：同步前置检测（降级放行）

    a = Answer(post_id=post_id, author_id=user.id, content=content)
    db.add(a)
    post.answer_count += 1
    post.last_answer_at = datetime.now()
    notify_service.push(db, post.author_id, 1, user.id, 1, post_id)  # 被回答
    db.commit()
    return _answer_dict(db, a, user)


def update_answer(db: Session, user: User, answer_id: int, content: str) -> dict:
    """编辑回答：作者 40301；已采纳锁定 40905；40913 AI 低质拦截（防编辑绕过）。"""
    a = get_answer_or_404(db, answer_id)
    if a.author_id != user.id:
        raise BizError(ErrCode.FORBIDDEN, "仅回答作者可编辑")
    if a.is_accepted:
        raise BizError(ErrCode.ANSWER_EDIT_LOCKED, "已被采纳的回答不可编辑")
    if contains_sensitive(content):
        raise BizError(ErrCode.SENSITIVE_WORD, "内容含违禁词")
    _check_quality(db, user, content)  # V1.3：编辑同样检测（防提交后改灌水）
    a.content = content
    db.commit()
    return _answer_dict(db, a, user)


def delete_answer(db: Session, user: User, answer_id: int) -> None:
    """删除回答：作者 40301；已采纳锁定 40906；维护 answer_count。"""
    a = get_answer_or_404(db, answer_id)
    if a.author_id != user.id:
        raise BizError(ErrCode.FORBIDDEN, "仅回答作者可删除")
    if a.is_accepted:
        raise BizError(ErrCode.ANSWER_DELETE_LOCKED, "已被采纳的回答不可删除")
    a.deleted_at = datetime.now()
    post = db.get(Post, a.post_id)
    if post is not None and post.answer_count > 0:
        post.answer_count -= 1
    notify_service.invalidate(db, 2, answer_id)  # 指向该回答的通知全部失效
    db.commit()


def list_answers(db: Session, post_id: int, viewer: User | None) -> list[dict]:
    """回答列表：最佳 > 采纳 > 点赞数 > 时间；已解决帖可继续回答（无状态过滤）。"""
    rows = (
        db.execute(
            select(Answer).where(Answer.post_id == post_id, Answer.deleted_at.is_(None))
        )
        .scalars()
        .all()
    )
    rows.sort(
        key=lambda a: (
            -a.is_best,
            -a.is_accepted,
            -a.like_count,
            -(a.created_at.timestamp() if a.created_at else 0),
        )
    )
    return [_answer_dict(db, a, viewer) for a in rows]


# ---- AI 可靠性评分（V1.3 reliability 场景）----


def generate_reliability_task(answer_id: int) -> None:
    """BackgroundTasks 入口：异步为回答生成 AI 可靠性评分；任何失败静默（字段保持 None，前端不渲染徽标）。

    编辑回答后内容变化 → 清空旧评分并重新生成（路由层挂载）。
    """
    from app.core.database import SessionLocal
    from app.gateway.client import LLMDegradedError, gateway

    with SessionLocal() as db:
        a = db.get(Answer, answer_id)
        if a is None or a.deleted_at is not None:
            return
        post = db.get(Post, a.post_id)
        if post is None or post.deleted_at is not None:
            return
        try:
            out = gateway.invoke(
                "reliability",
                {
                    "post_id": post.id,
                    "post_title": post.title,
                    "post_content": (post.content or "")[:1000],
                    "answer_text": (a.content or "")[:2000],
                },
            )
        except LLMDegradedError:
            return
        a = db.get(Answer, answer_id)  # 重取防并发过期
        if a is not None and a.deleted_at is None:
            a.ai_rel_score = out["score"]
            a.ai_rel_level = out["level"]
            db.commit()
