"""点赞与收藏 toggle：联合主键幂等，40910 评论不可收藏。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError, ErrCode
from app.models import Answer, Comment, Favorite, LikeRecord, Post, User
from app.modules.post import service as post_service


def _load_target(db: Session, target_type: int, target_id: int):
    """加载目标对象并返回 (对象, 计数字段名)。"""
    if target_type == 1:
        post_service.get_post_or_404(db, target_id)
        return db.get(Post, target_id), "like_count"
    if target_type == 2:
        a = db.get(Answer, target_id)
        if a is None or a.deleted_at is not None:
            raise BizError(ErrCode.NOT_FOUND, "回答不存在或已删除")
        return a, "like_count"
    if target_type == 3:
        c = db.get(Comment, target_id)
        if c is None or c.deleted_at is not None:
            raise BizError(ErrCode.NOT_FOUND, "评论不存在或已删除")
        return c, "like_count"
    raise BizError(ErrCode.BAD_REQUEST, "目标类型无效")


def toggle_like(db: Session, user: User, target_type: int, target_id: int) -> dict:
    """点赞/取消：存在记录则删除并减计数，否则插入并加计数。"""
    target, count_field = _load_target(db, target_type, target_id)
    existing = db.execute(
        select(LikeRecord).where(
            LikeRecord.user_id == user.id,
            LikeRecord.target_type == target_type,
            LikeRecord.target_id == target_id,
        )
    ).scalar_one_or_none()
    if existing:
        db.delete(existing)
        setattr(target, count_field, max(0, (getattr(target, count_field) or 0) - 1))
        liked = False
    else:
        db.add(LikeRecord(user_id=user.id, target_type=target_type, target_id=target_id))
        setattr(target, count_field, (getattr(target, count_field) or 0) + 1)
        liked = True
    db.commit()
    return {"liked": liked, "like_count": getattr(target, count_field)}


def toggle_favorite(db: Session, user: User, target_type: int, target_id: int) -> dict:
    """收藏/取消：仅 1 帖子 / 2 回答（40910 评论不可收藏）。"""
    if target_type == 3:
        raise BizError(ErrCode.FAVORITE_NOT_ALLOWED, "评论不可收藏")
    if target_type not in (1, 2):
        raise BizError(ErrCode.BAD_REQUEST, "目标类型无效")
    if target_type == 1:
        post_service.get_post_or_404(db, target_id)
    else:
        a = db.get(Answer, target_id)
        if a is None or a.deleted_at is not None:
            raise BizError(ErrCode.NOT_FOUND, "回答不存在或已删除")
    existing = db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.target_type == target_type,
            Favorite.target_id == target_id,
        )
    ).scalar_one_or_none()
    if existing:
        db.delete(existing)
        favorited = False
    else:
        db.add(Favorite(user_id=user.id, target_type=target_type, target_id=target_id))
        favorited = True
    db.commit()
    return {"favorited": favorited}
