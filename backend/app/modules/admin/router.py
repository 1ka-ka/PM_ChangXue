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


# ---- 商城商品管理（V1.15 个性化：新增/编辑/上下架）----


class ProductCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=200)
    price: int = Field(gt=0)
    stock: int = Field(default=-1, description="-1=不限量")
    image_url: str | None = Field(default=None, max_length=255)
    type: int = Field(default=1, ge=1, le=2, description="1虚拟 2实物")
    category: int = Field(default=0, ge=0, le=8, description="0无分类 1头衔 2徽章 3头像框 4气泡 5特效 6字体 7皮肤 8宠物")
    payload: str = Field(default="", max_length=100, description="展示载荷：文本/emoji/样式key")


@router.post("/admin/mall/products")
def create_product(
    body: ProductCreateIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """新增商品（个性化品类扩展入口：新槽位资源由此上架）。"""
    return ok(
        service.create_product(
            db,
            name=body.name,
            description=body.description,
            price=body.price,
            stock=body.stock,
            image_url=body.image_url,
            type_=body.type,
            category=body.category,
            payload=body.payload,
        )
    )


class ProductUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    price: int | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None)
    image_url: str | None = Field(default=None, max_length=255)
    category: int | None = Field(default=None, ge=0, le=8)
    payload: str | None = Field(default=None, max_length=100)
    enabled: int | None = Field(default=None, ge=0, le=1, description="0=下架 1=上架")


@router.put("/admin/mall/products/{product_id}")
def update_product(
    product_id: int,
    body: ProductUpdateIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """编辑/上下架商品：下架不影响已持有与佩戴，仅不可再兑换。"""
    return ok(
        service.update_product(
            db,
            product_id,
            name=body.name,
            description=body.description,
            price=body.price,
            stock=body.stock,
            image_url=body.image_url,
            category=body.category,
            payload=body.payload,
            enabled=body.enabled,
        )
    )


# ---- 系统账号自动运营（V1.13）----


@router.post("/admin/operation/run")
def operation_run(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """手动触发一轮运营（随机 1-3 个动作，不受配额/时段限制；用于演示与冷启动补充）。"""
    from app.modules.operation import service as op_service

    return ok(op_service.run_round(db, manual=True))


@router.get("/admin/operation/status")
def operation_status(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """运营状态：当日进度 / 配额 / 账号池 / 最近动作日志。"""
    from app.modules.operation import service as op_service

    return ok(op_service.status(db))
