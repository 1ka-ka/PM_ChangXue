"""V1.14 助人榜多维化：answer.accepted_at 采纳发生时间

Revision ID: b8c4d2f6a901
Revises: a7d2e9f4b816
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op

revision = "b8c4d2f6a901"
down_revision = "a7d2e9f4b816"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("answer", sa.Column("accepted_at", sa.DateTime(), nullable=True))
    # 回填存量：已采纳回答的 updated_at 近似采纳时间（采纳后禁止编辑，updated_at 即采纳时刻）
    op.execute("UPDATE answer SET accepted_at = updated_at WHERE is_accepted = 1")


def downgrade() -> None:
    op.drop_column("answer", "accepted_at")
