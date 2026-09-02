"""search 路由：接口 23 搜索（技术细节文档 §5.6）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams
from app.core.response import ok
from app.models import User
from app.modules.account.router import optional_user
from app.modules.search import service

router = APIRouter()


@router.get("/search")
def search(
    q: str | None = Query(None, max_length=50),
    tag_id: int | None = Query(None),
    page: PageParams = Depends(),
    viewer: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    return ok(service.search(db, viewer, q, tag_id, page.offset, page.limit))
