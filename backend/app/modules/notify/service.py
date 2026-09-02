"""站内通知：五类互动生成 + 软删 invalid 联动 + 列表/未读数/全部已读。

通知类型（技术细节文档 §3.4）：
1 被回答（目标=帖子）2 被评论（目标=被评论对象）3 被回复（目标=根评论）
4 被采纳（目标=回答）5 被点赞（目标=被赞对象）

target_type：1 帖子 / 2 回答 / 3 评论（与点赞/评论对象一致，前端据此直达）。

invalid 联动规则：对象被软删时，凡 target 指向该对象的通知统一置 invalid=1。
"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Notification, User
from app.modules.account.service import brief

TYPE_TEXT = {
    1: "回答了你的提问",
    2: "评论了你的内容",
    3: "回复了你的评论",
    4: "你的回答被采纳",
    5: "赞了你的内容",
}

UNREAD_CAP = 100  # >99 条的语义值


def push(
    db: Session, user_id: int, ntype: int, actor_id: int, target_type: int, target_id: int
) -> None:
    """生成通知（不 commit，由调用方事务编排）；自己触发的互动不通知。"""
    if user_id == actor_id:
        return
    db.add(
        Notification(
            user_id=user_id,
            type=ntype,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
        )
    )


def invalidate(db: Session, target_type: int, target_id: int) -> None:
    """对象软删时标记相关通知 invalid（不 commit）。"""
    db.execute(
        update(Notification)
        .where(Notification.target_type == target_type, Notification.target_id == target_id)
        .values(invalid=1)
    )


def _item(db: Session, n: Notification) -> dict:
    actor = db.get(User, n.actor_id)
    return {
        "id": n.id,
        "type": n.type,
        "type_text": TYPE_TEXT.get(n.type, "通知"),
        "actor": brief(actor) if actor else None,
        "target_type": n.target_type,
        "target_id": n.target_id,
        "is_read": bool(n.is_read),
        "invalid": bool(n.invalid),
        "created_at": n.created_at,
    }


def list_notifications(db: Session, user_id: int, offset: int, limit: int) -> dict:
    rows = (
        db.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.id.desc())
        )
        .scalars()
        .all()
    )
    return {"total": len(rows), "items": [_item(db, n) for n in rows[offset : offset + limit]]}


def unread_count(db: Session, user_id: int) -> int:
    """未读数：未读且未失效；>99 返回语义值 100。"""
    n = len(
        db.execute(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.is_read == 0,
                Notification.invalid == 0,
            )
        )
        .scalars()
        .all()
    )
    return min(n, UNREAD_CAP) if n > 99 else n


def read_all(db: Session, user_id: int) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == 0)
        .values(is_read=1)
    )
    db.commit()
