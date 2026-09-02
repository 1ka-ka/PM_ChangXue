"""moderation 路由：接口 30 提交举报（技术细节文档 §5.10）。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.models import User
from app.modules.moderation import service

router = APIRouter()


class ReportIn(BaseModel):
    target_type: int = Field(ge=1, le=3)
    target_id: int
    reason: int = Field(ge=1, le=5, description="1垃圾广告 2人身攻击 3色情低俗 4违法违规 5其他")
    detail: str = Field(default="", max_length=200)


@router.post("/reports")
def create_report(
    body: ReportIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.create_report(db, user, body.target_type, body.target_id, body.reason, body.detail)
    return ok(None)
