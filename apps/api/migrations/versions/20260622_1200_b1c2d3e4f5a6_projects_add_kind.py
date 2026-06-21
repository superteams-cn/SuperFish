"""projects: add kind column (推演类型分派)

Revision ID: b1c2d3e4f5a6
Revises: a88d44ea520a
Create Date: 2026-06-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a88d44ea520a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 存量行回落 social_opinion；server_default 保证旧数据与并发写入安全
    op.add_column(
        "projects",
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default="social_opinion",
        ),
    )
    op.create_index(op.f("ix_projects_kind"), "projects", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_kind"), table_name="projects")
    op.drop_column("projects", "kind")
