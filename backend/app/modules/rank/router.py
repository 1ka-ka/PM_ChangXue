"""rank 路由：接口 24 助人榜（技术细节文档 §5.7）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.modules.rank import service

router = APIRouter()


@router.get("/ranks")
def ranks(
    period: str = Query("week", pattern="^(week|month)$"),
    db: Session = Depends(get_db),
):
    return ok(service.list_ranks(db, period))
