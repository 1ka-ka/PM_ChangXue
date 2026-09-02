"""双层评论业务：二层封顶（40909）、级联软删。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BizError, ErrCode
from app.core.sensitive import contains_sensitive
from app.models import Answer, Comment, Post, User
from app.modules.post import service as post_service


def _validate_target(db: Session, target_type: int, target_id: int):
    """评论目标存在性：1 帖子 / 2 回答。"""
    if target_type == 1:
        post_service.get_post_or_404(db, target_id)
    elif target_type == 2:
        a = db.get(Answer, target_id)
        if a is None or a.deleted_at is not None:
            raise BizError(ErrCode.NOT_FOUND, "回答不存在或已删除")
    else:
        raise BizError(ErrCode.BAD_REQUEST, "评论目标类型无效")


def _comment_dict(db: Session, c: Comment) -> dict:
    author = db.get(User, c.author_id)
    reply_to = db.get(User, c.reply_to_user_id) if c.reply_to_user_id else None
    return {
        "id": c.id,
        "target_type": c.target_type,
        "target_id": c.target_id,
        "author_id": c.author_id,
        "author_nickname": author.nickname if author else "已注销",
        "parent_id": c.parent_id,
        "reply_to_user_id": c.reply_to_user_id,
        "reply_to_nickname": reply_to.nickname if reply_to else None,
        "content": c.content,
        "like_count": c.like_count,
        "is_liked": False,  # 列表组装时填充
        "created_at": c.created_at,
    }


def create_comment(
    db: Session,
    user: User,
    target_type: int,
    target_id: int,
    content: str,
    parent_id: int | None,
    reply_to_user_id: int | None,
) -> dict:
    """发表评论：40909 parent 必须指向根评论（二层封顶）。"""
    _validate_target(db, target_type, target_id)
    if contains_sensitive(content):
        raise BizError(ErrCode.SENSITIVE_WORD, "内容含违禁词")
    if not content or len(content) > settings.COMMENT_MAX_LEN:
        raise BizError(ErrCode.BAD_REQUEST, f"评论内容须为 1-{settings.COMMENT_MAX_LEN} 字")
    if parent_id is not None:
        parent = db.get(Comment, parent_id)
        if parent is None or parent.deleted_at is not None:
            raise BizError(ErrCode.NOT_FOUND, "被回复的评论不存在")
        if parent.parent_id is not None:
            raise BizError(ErrCode.COMMENT_NESTING, "评论最多两层")
        if (parent.target_type, parent.target_id) != (target_type, target_id):
            raise BizError(ErrCode.BAD_REQUEST, "回复目标与评论对象不一致")

    c = Comment(
        target_type=target_type,
        target_id=target_id,
        author_id=user.id,
        parent_id=parent_id,
        reply_to_user_id=reply_to_user_id,
        content=content,
    )
    db.add(c)
    db.commit()
    return _comment_dict(db, c)


def delete_comment(db: Session, user: User, comment_id: int) -> None:
    """删除评论：作者 40301；级联软删其全部回复。"""
    c = db.get(Comment, comment_id)
    if c is None or c.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "评论不存在或已删除")
    if c.author_id != user.id:
        raise BizError(ErrCode.FORBIDDEN, "仅评论作者可删除")
    now = datetime.now()
    c.deleted_at = now
    replies = db.execute(
        select(Comment).where(Comment.parent_id == comment_id, Comment.deleted_at.is_(None))
    ).scalars().all()
    for r in replies:
        r.deleted_at = now
    db.commit()


def list_comments(db: Session, target_type: int, target_id: int) -> list[dict]:
    """评论树：根评论按时间正序，replies 挂接。"""
    roots = (
        db.execute(
            select(Comment).where(
                Comment.target_type == target_type,
                Comment.target_id == target_id,
                Comment.parent_id.is_(None),
                Comment.deleted_at.is_(None),
            ).order_by(Comment.id)
        )
        .scalars()
        .all()
    )
    replies = (
        db.execute(
            select(Comment).where(
                Comment.target_type == target_type,
                Comment.target_id == target_id,
                Comment.parent_id.is_not(None),
                Comment.deleted_at.is_(None),
            ).order_by(Comment.id)
        )
        .scalars()
        .all()
    )
    by_parent: dict[int, list[dict]] = {}
    for r in replies:
        by_parent.setdefault(r.parent_id, []).append(_comment_dict(db, r))
    return [_comment_dict(db, c) | {"replies": by_parent.get(c.id, [])} for c in roots]
