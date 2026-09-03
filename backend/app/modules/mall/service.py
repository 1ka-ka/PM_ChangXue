"""积分商城业务逻辑（V1.8）：商品列表/兑换/我的兑换记录。

设计要点：
- 兑换原子性：锁商品行 → 落兑换记录（快照名/价）→ 扣积分（source=7）→ 减库存，
  同一事务 commit；任一步失败整体回滚（积分不足抛 40902，库存/下架抛 40916）；
- 库存语义：stock=-1 不限量；stock=0 或 enabled=0 → 40916；
- 虚拟商品（type=1）兑换即完成（status=2）；实物（type=2）待发货（status=1，V2 收货地址）；
- ref_type=4（商城兑换记录），扩展通用对象类型枚举（1帖 2答 3评 4兑换）。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError, ErrCode
from app.models import MallExchange, MallProduct, User
from app.modules.credit import service as credit_service
from app.modules.credit.sources import CreditSource

REF_TYPE_EXCHANGE = 4


def _lock_product(db: Session, product_id: int) -> MallProduct:
    """锁定商品行；MySQL FOR UPDATE 防超卖，SQLite 单写者天然串行。"""
    if db.bind.dialect.name == "mysql":
        return db.execute(
            select(MallProduct).where(MallProduct.id == product_id).with_for_update()
        ).scalar_one_or_none()
    return db.get(MallProduct, product_id)


def list_products(db: Session, offset: int, limit: int) -> dict:
    """在售商品列表（enabled=1，id 正序稳定分页）。"""
    rows = (
        db.execute(select(MallProduct).where(MallProduct.enabled == 1).order_by(MallProduct.id))
        .scalars()
        .all()
    )
    return {
        "total": len(rows),
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "stock": p.stock,
                "image_url": p.image_url,
                "type": p.type,
            }
            for p in rows[offset : offset + limit]
        ],
    }


def exchange(db: Session, user: User, product_id: int) -> dict:
    """兑换商品：单事务完成扣分+减库存+落记录；返回兑换结果。"""
    product = _lock_product(db, product_id)
    if product is None or product.enabled != 1:
        raise BizError(ErrCode.MALL_OUT_OF_STOCK, "商品不存在或已下架")
    if product.stock != -1 and product.stock <= 0:
        raise BizError(ErrCode.MALL_OUT_OF_STOCK, "商品库存不足")

    ex = MallExchange(
        user_id=user.id,
        product_id=product.id,
        product_name=product.name,  # 快照：商品可改名/改价
        cost=product.price,
        status=2 if product.type == 1 else 1,  # 虚拟即完成，实物待发货
    )
    db.add(ex)
    db.flush()  # 取记录 id 供流水引用

    # 扣积分（不足抛 40902，事务整体回滚，库存不减）
    credit_service.deduct(
        db,
        user.id,
        CreditSource.SHOP,
        product.price,
        ref_type=REF_TYPE_EXCHANGE,
        ref_id=ex.id,
        note=f"商城兑换（{product.name}）",
    )

    if product.stock != -1:
        product.stock -= 1
    db.commit()
    return {
        "exchange_id": ex.id,
        "product_name": ex.product_name,
        "cost": ex.cost,
        "status": ex.status,
        "created_at": ex.created_at,
    }


def my_exchanges(db: Session, uid: int, offset: int, limit: int) -> dict:
    """我的兑换记录（id 倒序分页）。"""
    rows = (
        db.execute(
            select(MallExchange).where(MallExchange.user_id == uid).order_by(MallExchange.id.desc())
        )
        .scalars()
        .all()
    )
    return {
        "total": len(rows),
        "items": [
            {
                "id": e.id,
                "product_id": e.product_id,
                "product_name": e.product_name,
                "cost": e.cost,
                "status": e.status,
                "created_at": e.created_at,
            }
            for e in rows[offset : offset + limit]
        ],
    }
