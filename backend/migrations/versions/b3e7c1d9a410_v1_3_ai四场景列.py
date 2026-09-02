"""V1.3 AI 四场景列：post.ai_answer* / answer.ai_rel_* / report.ai_*

Revision ID: b3e7c1d9a410
Revises: afeffa03da10
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op

revision = "b3e7c1d9a410"
down_revision = "afeffa03da10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("post", sa.Column("ai_answer", sa.Text(), nullable=True, comment="AI 参考回答（缓存）"))
    op.add_column("post", sa.Column("ai_answer_at", sa.DateTime(), nullable=True, comment="AI 参考回答生成时间"))
    op.add_column("answer", sa.Column("ai_rel_score", sa.Integer(), nullable=True, comment="AI 可靠性评分 0-100"))
    op.add_column("answer", sa.Column("ai_rel_level", sa.String(length=10), nullable=True, comment="AI 可靠性等级 高/中/存疑"))
    op.add_column("report", sa.Column("ai_level", sa.String(length=10), nullable=True, comment="AI 违规分级 极高/高/低"))
    op.add_column("report", sa.Column("ai_violation_type", sa.String(length=50), nullable=True, comment="AI 判定违规类型"))


def downgrade() -> None:
    op.drop_column("report", "ai_violation_type")
    op.drop_column("report", "ai_level")
    op.drop_column("answer", "ai_rel_level")
    op.drop_column("answer", "ai_rel_score")
    op.drop_column("post", "ai_answer_at")
    op.drop_column("post", "ai_answer")
