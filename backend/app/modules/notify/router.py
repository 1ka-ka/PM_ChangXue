"""notify 路由：接口 25-27 通知列表/未读计数/全部已读（技术细节文档 §5.8）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams, get_current_user
from app.core.response import ok
from app.models import User
from app.modules.notify import service

router = APIRouter()


@router.get("/notifications")
def notifications(
    page: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(service.list_notifications(db, user.id, page.offset, page.limit))


@router.get("/notifications/unread-count")
def unread_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok({"count": service.unread_count(db, user.id)})


@router.post("/notifications/read-all")
def read_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.read_all(db, user.id)
    return ok(None)
