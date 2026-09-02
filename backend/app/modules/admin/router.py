"""admin 路由：接口 31-38 管理后台（技术细节文档 §5.11，全部 require_admin）。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams, require_admin
from app.core.response import ok
from app.models import User
from app.modules.admin import service

router = APIRouter()


@router.get("/admin/reports")
def reports(
    status: int | None = Query(None, description="0待处理 1已处置 2驳回，缺省全部"),
    page: PageParams = Depends(),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(service.list_reports(db, status, page.offset, page.limit))


class ActionIn(BaseModel):
    action: str = Field(pattern="^(delete|ban|recall_credit|dismiss)$")
    reason: str = Field(min_length=1, max_length=200)
    ban_days: int | None = Field(None, description="封号天数 1/7，0=永久（action=ban 必填）")
    amount: int | None = Field(None, gt=0, description="追回积分（action=recall_credit 必填）")


@router.post("/admin/reports/{report_id}/action")
def act_report(
    report_id: int,
    body: ActionIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service.act(db, admin, report_id, body.action, body.reason, body.ban_days, body.amount)
    return ok(None)


@router.get("/admin/tags")
def tags(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(service.list_tags(db))


class TagCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    sort: int = 0


@router.post("/admin/tags")
def create_tag(
    body: TagCreateIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(service.create_tag(db, body.name, body.sort))


class TagUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=20)
    sort: int | None = None
    enabled: int | None = Field(default=None, ge=0, le=1)


@router.put("/admin/tags/{tag_id}")
def update_tag(
    tag_id: int,
    body: TagUpdateIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(service.update_tag(db, tag_id, body.name, body.sort, body.enabled))


@router.get("/admin/logs")
def logs(
    admin_id: int | None = Query(None),
    action: int | None = Query(None, ge=1, le=8),
    page: PageParams = Depends(),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(service.list_logs(db, admin_id, action, page.offset, page.limit))


@router.get("/admin/stats")
def stats(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(service.stats(db))
