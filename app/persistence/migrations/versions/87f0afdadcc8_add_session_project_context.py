"""add session project context

Revision ID: 87f0afdadcc8
Revises: 24245d3d7107
Create Date: 2026-10-31 15:22:28.958233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '87f0afdadcc8'
down_revision: Union[str, Sequence[str], None] = '24245d3d7107'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "context_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "sessions",
        "context_state",
    )