"""私信业务逻辑（V1.7）：会话列表/消息拉取（自动已读）/发送/未读总数。

设计要点：
- 会话唯一：user_a_id < user_b_id，唯一键保证一对用户一会话；
- 游标已读：会话内各持 last_read_id，未读 = 对方发的、id > 我游标的消息数；
  打开会话拉取消息时自动把游标推到最新消息；
- 软删用户不可收发（40002）；自己不能给自己发（40001）。
"""

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError, ErrCode
from app.core.sensitive import contains_sensitive
from app.models import DmConversation, DmMessage, User
from app.modules.account.service import brief


def _unread_subquery(uid: int):
    """子查询：各会话中该用户的未读数（对方发的、id 超过本人游标）。"""
    my_read = case(
        (DmConversation.user_a_id == uid, DmConversation.a_last_read_id),
        else_=DmConversation.b_last_read_id,
    )
    return (
        select(DmMessage.conversation_id, func.count().label("unread"))
        .join(DmConversation, DmConversation.id == DmMessage.conversation_id)
        .where(DmMessage.sender_id != uid, DmMessage.id > my_read)
        .group_by(DmMessage.conversation_id)
    ).subquery()


def _get_or_create_conversation(db: Session, uid_a: int, uid_b: int) -> DmConversation:
    """取或建会话（约定小 id 为 a）；不 commit，由调用方事务编排。"""
    lo, hi = min(uid_a, uid_b), max(uid_a, uid_b)
    conv = db.execute(
        select(DmConversation).where(DmConversation.user_a_id == lo, DmConversation.user_b_id == hi)
    ).scalar_one_or_none()
    if conv is None:
        conv = DmConversation(user_a_id=lo, user_b_id=hi)
        db.add(conv)
        db.flush()  # 取 id
    return conv


def _peer_id(conv: DmConversation, uid: int) -> int:
    return conv.user_b_id if conv.user_a_id == uid else conv.user_a_id


def send(db: Session, sender: User, to_user_id: int, content: str) -> dict:
    """发送私信：校验 → 建会话 → 落消息 → 推进发送方游标；返回消息体。"""
    if to_user_id == sender.id:
        raise BizError(ErrCode.BAD_REQUEST, "不能给自己发私信")
    if contains_sensitive(content):
        raise BizError(ErrCode.SENSITIVE_WORD, "私信内容含违禁词")
    peer = db.get(User, to_user_id)
    if peer is None or peer.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "接收方不存在")

    conv = _get_or_create_conversation(db, sender.id, to_user_id)
    msg = DmMessage(conversation_id=conv.id, sender_id=sender.id, content=content)
    db.add(msg)
    db.flush()
    conv.last_message_id = msg.id  # updated_at 由 onupdate 维护
    if conv.user_a_id == sender.id:  # 自己发的无需未读
        conv.a_last_read_id = msg.id
    else:
        conv.b_last_read_id = msg.id
    db.commit()
    return {
        "id": msg.id,
        "conversation_id": conv.id,
        "content": msg.content,
        "created_at": msg.created_at,
    }


def list_conversations(db: Session, uid: int, offset: int, limit: int) -> dict:
    """会话列表：updated_at 倒序，含对方信息/最后一条摘要/未读数。"""
    unread_sq = _unread_subquery(uid)
    rows = (
        db.execute(
            select(DmConversation, func.coalesce(unread_sq.c.unread, 0))
            .outerjoin(unread_sq, unread_sq.c.conversation_id == DmConversation.id)
            .where(or_(DmConversation.user_a_id == uid, DmConversation.user_b_id == uid))
            .order_by(DmConversation.updated_at.desc())
        )
        .all()
    )
    items = []
    for conv, unread in rows[offset : offset + limit]:
        peer = db.get(User, _peer_id(conv, uid))
        last = db.get(DmMessage, conv.last_message_id) if conv.last_message_id else None
        items.append(
            {
                "conversation_id": conv.id,
                "peer": brief(peer) if peer else None,
                "last_content": last.content[:60] if last else None,
                "last_time": conv.updated_at,
                "unread": int(unread),
            }
        )
    return {"total": len(rows), "items": items}


def list_messages(db: Session, uid: int, conversation_id: int, offset: int, limit: int) -> dict:
    """消息列表（id 倒序分页）；拉取即自动把本人已读游标推到最新。"""
    conv = db.get(DmConversation, conversation_id)
    if conv is None or uid not in (conv.user_a_id, conv.user_b_id):
        raise BizError(ErrCode.NOT_FOUND, "会话不存在")

    msgs = (
        db.execute(
            select(DmMessage)
            .where(DmMessage.conversation_id == conversation_id)
            .order_by(DmMessage.id.desc())
        )
        .scalars()
        .all()
    )
    if msgs:  # 打开会话即已读
        if conv.user_a_id == uid:
            conv.a_last_read_id = max(conv.a_last_read_id, msgs[0].id)
        else:
            conv.b_last_read_id = max(conv.b_last_read_id, msgs[0].id)
        db.commit()

    return {
        "total": len(msgs),
        "items": [
            {"id": m.id, "sender_id": m.sender_id, "content": m.content, "created_at": m.created_at}
            for m in msgs[offset : offset + limit]
        ],
    }


def unread_count(db: Session, uid: int) -> int:
    """总未读私信数（跨会话求和）。"""
    unread_sq = _unread_subquery(uid)
    total = db.execute(select(func.coalesce(func.sum(unread_sq.c.unread), 0))).scalar_one()
    return int(total)
