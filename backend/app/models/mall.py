"""积分商城表（V1.8）：mall_product / mall_exchange（虚拟商品闭环 + 实物预留）。
V1.15 个性化：mall_product 增 category/payload，新增 user_item 背包表。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt

# 个性化品类（V1.15）：0=无分类（普通虚拟/实物商品）；1-8 与佩戴槽位一一对应。
# 新增品类只需在此枚举追加 + 前端加渲染样式，无需改表结构。
CATEGORY_TITLE = 1  # 头衔：昵称旁小标签，payload=显示文本（空则用商品名）
CATEGORY_BADGE = 2  # 徽章：emoji 徽章，payload=emoji
CATEGORY_FRAME = 3  # 头像框：payload=样式 key（gold/silver/blue/rose）
CATEGORY_BUBBLE = 4  # 气泡：聊天气泡样式，payload=样式 key
CATEGORY_EFFECT = 5  # 特效：昵称特效，payload=样式 key（glow/shine/flame）
CATEGORY_FONT = 6  # 字体：payload=样式 key（V1.16 启用）
CATEGORY_SKIN = 7  # 皮肤：页面主题包，payload=样式 key（V1.16 启用）
CATEGORY_PET = 8  # 宠物：主页挂件，payload=emoji（V1.17 启用）

# 佩戴槽位 → 商城品类（V1.15）：槽位名即个性化模块的通用键，新增品类在此追加即可。
SLOT_CATEGORY = {
    "title": CATEGORY_TITLE,
    "badge": CATEGORY_BADGE,
    "frame": CATEGORY_FRAME,
    "bubble": CATEGORY_BUBBLE,
    "effect": CATEGORY_EFFECT,
    "font": CATEGORY_FONT,
    "skin": CATEGORY_SKIN,
    "pet": CATEGORY_PET,
}


class MallProduct(Base):
    __tablename__ = "mall_product"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    price: Mapped[int] = mapped_column(Integer, nullable=False)  # 积分售价（正整数）
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)  # -1=不限量
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)  # 1虚拟 2实物
    category: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)  # 个性化品类（见上方枚举）
    payload: Mapped[str] = mapped_column(String(100), nullable=False, default="")  # 展示载荷：文本/emoji/样式 key
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = ({"comment": "商城商品：虚拟权益 + 实物文创（收货地址 V2 预留）"},)


class UserItem(Base):
    """背包（V1.15）：虚拟商品兑换所得，永久持有；佩戴状态存 user.equipped 快照。"""

    __tablename__ = "user_item"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInt, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uk_user_product"),
        {"comment": "背包：虚拟商品永久持有，同款唯一"},
    )


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
