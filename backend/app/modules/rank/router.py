"""rank 路由：接口 24 助人榜（技术细节文档 §5.7 + V1.14 多维化）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import BizError, ErrCode
from app.core.response import ok
from app.modules.rank import service

router = APIRouter()


@router.get("/ranks")
def ranks(
    period: str = Query("week", pattern="^(day|week|month)$"),
    metric: str = Query("gratitude", pattern="^(gratitude|answers|accepts)$"),
    db: Session = Depends(get_db),
):
    """助人榜：gratitude=感谢值周/月快照（原有）；answers/accepts=回答数/采纳数日/周/月实时榜（V1.14）。"""
    if metric == "gratitude":
        if period == "day":
            raise BizError(ErrCode.BAD_REQUEST, "感谢值榜仅支持周榜/月榜")
        return ok(service.list_ranks(db, period))
    return ok(service.list_live_ranks(db, metric, period))
