"""add_outreach_message_provider_columns

Revision ID: 7b1bfbea3bda
Revises: 1a585c4b68a1
Create Date: 2026-05-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b1bfbea3bda"
down_revision: Union[str, None] = "1a585c4b68a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add provider tracking columns to outreach_messages
    op.add_column("outreach_messages", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("outreach_messages", sa.Column("provider_message_id", sa.String(length=255), nullable=True))
    op.add_column("outreach_messages", sa.Column("to_email", sa.String(length=320), nullable=True))
    op.add_column("outreach_messages", sa.Column("error", sa.String(length=2048), nullable=True))

    # Add provider tracking columns to replies
    op.add_column("replies", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("replies", sa.Column("provider_inbound_id", sa.String(length=255), nullable=True))

    # Add indexes for provider lookups
    op.create_index("idx_replies_lead", "replies", ["lead_id"], unique=False)
    op.create_index("idx_replies_provider_inbound", "replies", ["provider_inbound_id"], unique=False)


def downgrade() -> None:
    # Remove indexes
    op.drop_index("idx_replies_provider_inbound", table_name="replies")
    op.drop_index("idx_replies_lead", table_name="replies")

    # Remove reply columns
    op.drop_column("replies", "provider_inbound_id")
    op.drop_column("replies", "provider")

    # Remove outreach_message columns
    op.drop_column("outreach_messages", "error")
    op.drop_column("outreach_messages", "to_email")
    op.drop_column("outreach_messages", "provider_message_id")
    op.drop_column("outreach_messages", "provider")