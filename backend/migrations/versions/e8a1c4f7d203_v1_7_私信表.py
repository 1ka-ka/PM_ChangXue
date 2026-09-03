"""V1.7 私信表：dm_conversation / dm_message（一对一私信，游标已读）

Revision ID: e8a1c4f7d203
Revises: c5f8a2e6b901
Create Date: 2026-09-03
"""

import sqlalchemy as sa
from alembic import op

revision = "e8a1c4f7d203"
down_revision = "c5f8a2e6b901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dm_conversation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_a_id", sa.BigInteger(), nullable=False),
        sa.Column("user_b_id", sa.BigInteger(), nullable=False),
        sa.Column("a_last_read_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("b_last_read_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_message_id", sa.BigInteger(), nullable=True),
        # 时间戳统一 Python 侧 default/onupdate（SQLite CURRENT_TIMESTAMP 为 UTC，勿用 server_default）
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_a_id", "user_b_id", name="uk_dm_user_pair"),
        comment="私信会话：一对用户唯一（a<b），游标式已读",
    )
    op.create_index("idx_dm_conv_a", "dm_conversation", ["user_a_id", "updated_at"])
    op.create_index("idx_dm_conv_b", "dm_conversation", ["user_b_id", "updated_at"])

    op.create_table(
        "dm_message",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["conversation_id"], ["dm_conversation.id"]),
        comment="私信消息：纯文本，已读由会话游标计算",
    )
    op.create_index("idx_dm_msg_conv", "dm_message", ["conversation_id", "id"])


def downgrade() -> None:
    # MySQL：FK 依赖索引，drop_table 会连索引一并删除，单独 drop_index 会报 1553
    op.drop_table("dm_message")
    op.drop_table("dm_conversation")
