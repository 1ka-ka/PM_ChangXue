"""moderation 路由：接口 30 提交举报（技术细节文档 §5.10）。

V1.3：提交后异步生成 AI 违规分级（moderation 场景）辅助管理员分诊。
"""

from fastapi import APIRouter, BackgroundTasks, Depends
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
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report_id = service.create_report(db, user, body.target_type, body.target_id, body.reason, body.detail)
    # V1.3：异步 AI 违规分级（LLM 关闭/失败时任务内部静默）
    background_tasks.add_task(service.moderate_report_task, report_id)
    return ok(None)
