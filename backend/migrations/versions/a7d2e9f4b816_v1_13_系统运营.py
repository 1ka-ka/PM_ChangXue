"""V1.13 系统账号自动运营：user.is_op 标记列 + operation_log 表

Revision ID: a7d2e9f4b816
Revises: f2b6d9a3c514
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op

from app.core.database import BigInt

revision = "a7d2e9f4b816"
down_revision = "f2b6d9a3c514"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("is_op", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "operation_log",
        sa.Column("id", BigInt(), autoincrement=True, nullable=False),
        sa.Column("user_id", BigInt(), nullable=True),
        sa.Column("action", sa.SmallInteger(), nullable=False),
        sa.Column("ok", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("target_type", sa.SmallInteger(), nullable=True),
        sa.Column("target_id", BigInt(), nullable=True),
        sa.Column("detail", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        comment="系统运营动作日志：配额统计（action 1-6）+ 后台展示",
    )
    op.create_index("idx_op_date", "operation_log", ["created_at"])
    op.create_index("idx_op_user", "operation_log", ["user_id", "id"])


def downgrade() -> None:
    op.drop_index("idx_op_user", table_name="operation_log")
    op.drop_index("idx_op_date", table_name="operation_log")
    op.drop_table("operation_log")
    op.drop_column("user", "is_op")
