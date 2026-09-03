"""message 路由（V1.7 私信）：会话列表/消息列表/发送/未读总数。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams, get_current_user
from app.core.response import ok
from app.models import User
from app.modules.message import service
from app.modules.message.schemas import DmSendIn

router = APIRouter()


@router.get("/messages/conversations")
def conversations(
    page: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的会话列表（updated_at 倒序，含对方信息/最后一条/未读数）。"""
    return ok(service.list_conversations(db, user.id, page.offset, page.limit))


@router.get("/messages/conversations/{conversation_id}")
def messages(
    conversation_id: int,
    page: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """会话消息列表（id 倒序分页，拉取即已读）。"""
    return ok(service.list_messages(db, user.id, conversation_id, page.offset, page.limit))


@router.post("/messages")
def send(
    body: DmSendIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发送私信（纯文本 1-500 字）。"""
    return ok(service.send(db, user, body.to_user_id, body.content))


@router.get("/messages/unread-count")
def unread_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """总未读私信数（顶栏角标）。"""
    return ok({"count": service.unread_count(db, user.id)})
