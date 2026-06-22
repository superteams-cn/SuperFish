"""projects: add narrative_mode column (剧本推演模式 free/faithful)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-22 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "narrative_mode",
            sa.String(length=16),
            nullable=False,
            server_default="free",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "narrative_mode")
