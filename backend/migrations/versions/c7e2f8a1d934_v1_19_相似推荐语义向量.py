"""V1.19 相似推荐语义升级：post.embedding 语义向量列（发帖时异步计算，存量走回填脚本）

Revision ID: c7e2f8a1d934
Revises: d3f7a9c2e5b1
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import JSON

revision = "c7e2f8a1d934"
down_revision = "d3f7a9c2e5b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 标题+正文前 200 字的语义向量（与 user.equipped 同款 mysql.JSON，SQLite 兼容）
    op.add_column("post", sa.Column("embedding", JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("post", "embedding")
