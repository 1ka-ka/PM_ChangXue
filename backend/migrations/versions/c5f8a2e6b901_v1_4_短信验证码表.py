"""V1.4 短信验证码表：sms_code（发送频控 + 一次性校验）

Revision ID: c5f8a2e6b901
Revises: b3e7c1d9a410
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op

revision = "c5f8a2e6b901"
down_revision = "b3e7c1d9a410"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sms_code",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("scene", sa.SmallInteger(), nullable=False, comment="2登录 3找回密码"),
        sa.Column("used", sa.SmallInteger(), nullable=False, server_default="0", comment="0未用 1已用"),
        sa.Column("expired_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        comment="短信验证码：60s 频控 + 日限额 + TTL 过期",
    )
    op.create_index("idx_sms_phone_scene", "sms_code", ["phone", "scene"])
    op.create_index("idx_sms_phone_created", "sms_code", ["phone", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_sms_phone_created", table_name="sms_code")
    op.drop_index("idx_sms_phone_scene", table_name="sms_code")
    op.drop_table("sms_code")
