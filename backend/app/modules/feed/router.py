"""feed 路由：接口 13 广场列表（技术细节文档 §5.2）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams
from app.core.response import ok
from app.modules.feed import service

router = APIRouter()


@router.get("/feed")
def feed(
    tab: str = Query("latest", pattern="^(latest|unsolved|recommend)$"),
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    return ok(service.list_feed(db, tab, page.offset, page.limit))
