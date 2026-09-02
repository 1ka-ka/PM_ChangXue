"""tracking 路由：接口 39 埋点批量上报（技术细节文档 §5.12，sendBeacon 兼容）。

- 限流 60 次/分/IP → 超限 BizError(40006, http 429)
- 成功/限流均返回响应信封外的语义：文档约定 204（空 body）
- 落库失败静默（同样 204，不影响业务）
"""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import BizError, ErrCode
from app.models import User
from app.modules.account.router import optional_user
from app.modules.tracking import service

router = APIRouter()


class EventIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    props: dict | None = None


class BatchIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=20)


@router.post("/events/batch")
def events_batch(
    body: BatchIn,
    request: Request,
    response: Response,
    viewer: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    if not service.limiter.allow(ip):
        raise BizError(ErrCode.RATE_LIMITED, "请求过于频繁，请稍后再试", http_status=429)
    # 失败静默：无论落库结果一律 204
    service.ingest_batch(db, viewer, [e.model_dump() for e in body.events])
    response.status_code = 204
    return None
