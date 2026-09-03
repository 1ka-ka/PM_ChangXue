"""mall 路由（V1.8 积分商城）：商品列表/兑换/我的兑换记录。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams, get_current_user
from app.core.response import ok
from app.models import User
from app.modules.mall import service
from app.modules.mall.schemas import ExchangeIn

router = APIRouter()


@router.get("/mall/products")
def products(page: PageParams = Depends(), db: Session = Depends(get_db)):
    """在售商品列表（无需登录可浏览）。"""
    return ok(service.list_products(db, page.offset, page.limit))


@router.post("/mall/exchange")
def exchange(
    body: ExchangeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """兑换商品（单事务：扣积分 source=7 + 减库存 + 落记录）。"""
    return ok(service.exchange(db, user, body.product_id))


@router.get("/mall/exchanges")
def exchanges(
    page: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的兑换记录（id 倒序分页）。"""
    return ok(service.my_exchanges(db, user.id, page.offset, page.limit))
