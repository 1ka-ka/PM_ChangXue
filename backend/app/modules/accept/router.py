"""accept 路由：接口 17-18（技术细节文档 §5.4）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.models import User
from app.modules.accept import service

router = APIRouter()


@router.post("/answers/{answer_id}/accept")
def accept_answer(
    answer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(service.accept(db, user, answer_id))


@router.post("/answers/{answer_id}/set-best")
def set_best(
    answer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(service.set_best(db, user, answer_id))
