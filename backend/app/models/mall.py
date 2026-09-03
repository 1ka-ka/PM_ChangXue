"""积分商城表（V1.8）：mall_product / mall_exchange（虚拟商品闭环 + 实物预留）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class MallProduct(Base):
    __tablename__ = "mall_product"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    price: Mapped[int] = mapped_column(Integer, nullable=False)  # 积分售价（正整数）
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)  # -1=不限量
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)  # 1虚拟 2实物
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = ({"comment": "商城商品：虚拟权益 + 实物文创（收货地址 V2 预留）"},)


class MallExchange(Base):
    __tablename__ = "mall_exchange"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInt, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    product_name: Mapped[str] = mapped_column(String(50), nullable=False)  # 快照（商品可改名）
    cost: Mapped[int] = mapped_column(Integer, nullable=False)  # 成交价快照
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)  # 1待发货 2已完成
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = ({"comment": "兑换记录：同事务扣分（source=7 商城）+ 减库存；虚拟商品直接完成"},)
