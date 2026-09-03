"""V1.8 积分商城表：mall_product / mall_exchange

Revision ID: f2b6d9a3c514
Revises: e8a1c4f7d203
Create Date: 2026-09-03
"""

import sqlalchemy as sa
from alembic import op

revision = "f2b6d9a3c514"
down_revision = "e8a1c4f7d203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mall_product",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("image_url", sa.String(length=255), nullable=True),
        sa.Column("type", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        comment="商城商品：虚拟权益 + 实物文创（收货地址 V2 预留）",
    )

    op.create_table(
        "mall_exchange",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("product_name", sa.String(length=50), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        comment="兑换记录：同事务扣分（source=7 商城）+ 减库存；虚拟商品直接完成",
    )
    op.create_index("idx_mall_ex_user", "mall_exchange", ["user_id", "id"])


def downgrade() -> None:
    op.drop_index("idx_mall_ex_user", table_name="mall_exchange")
    op.drop_table("mall_exchange")
    op.drop_table("mall_product")
