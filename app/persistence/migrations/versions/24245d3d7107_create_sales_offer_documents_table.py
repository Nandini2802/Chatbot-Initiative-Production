"""create sales offer documents table

Revision ID: 24245d3d7107
Revises: 3707b90bd862
Create Date: 2026-10-29 11:37:15.142614

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '24245d3d7107'
down_revision: Union[str, Sequence[str], None] = '3707b90bd862'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sales_offer_documents",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("sales_offer_doc_id", sa.String(255), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_sales_offer_documents_user_session",
        "sales_offer_documents",
        ["user_id", "session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sales_offer_documents_user_session",
        table_name="sales_offer_documents",
    )
    op.drop_table("sales_offer_documents")
