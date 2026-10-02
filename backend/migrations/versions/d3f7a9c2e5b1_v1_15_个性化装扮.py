"""V1.15 个性化装扮：user.equipped 佩戴快照 + mall_product.category/payload + user_item 背包表

Revision ID: d3f7a9c2e5b1
Revises: b8c4d2f6a901
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import JSON

from app.core.database import BigInt

revision = "d3f7a9c2e5b1"
down_revision = "b8c4d2f6a901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 佩戴快照 JSON（与 S1 theme_config 同款 mysql.JSON，SQLite 兼容）
    op.add_column("user", sa.Column("equipped", JSON(), nullable=True))

    # 商城商品：品类 + 展示载荷
    op.add_column("mall_product", sa.Column("category", sa.SmallInteger(), nullable=False, server_default="0"))
    op.add_column("mall_product", sa.Column("payload", sa.String(length=100), nullable=False, server_default=""))
    # 存量种子商品回填品类（学霸头衔→头衔，问答之星→徽章）
    op.execute("UPDATE mall_product SET category = 1, payload = '学霸' WHERE name = '学霸头衔·7天'")
    op.execute("UPDATE mall_product SET category = 2, payload = '⭐' WHERE name = '限定徽章·问答之星'")

    # 背包表
    op.create_table(
        "user_item",
        sa.Column("id", BigInt(), autoincrement=True, nullable=False),
        sa.Column("user_id", BigInt(), nullable=False),
        sa.Column("product_id", BigInt(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uk_user_product"),
        comment="背包：虚拟商品永久持有，同款唯一",
    )
    op.create_index("ix_user_item_user_id", "user_item", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_item_user_id", table_name="user_item")
    op.drop_table("user_item")
    op.drop_column("mall_product", "payload")
    op.drop_column("mall_product", "category")
    op.drop_column("user", "equipped")
