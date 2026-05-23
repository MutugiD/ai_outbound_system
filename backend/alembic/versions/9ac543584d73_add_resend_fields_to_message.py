"""add resend fields to message

Revision: 9ac543584d73
Revises: 2725d4eb8a75
Create Date: 2026-05-24 01:53:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9ac543584d73"
down_revision = "2725d4eb8a75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add resend_id column with index
    op.add_column("outreach_messages", sa.Column("resend_id", sa.String(), nullable=True, comment="Resend message ID for tracking"))
    op.add_column("outreach_messages", sa.Column("error_message", sa.String(), nullable=True, comment="Error message if send failed"))
    op.add_column("outreach_messages", sa.Column("scheduled_at", sa.DateTime(), nullable=True, comment="When to send the message"))
    op.create_index("ix_outreach_messages_resend_id", "outreach_messages", ["resend_id"])


def downgrade() -> None:
    op.drop_index("ix_outreach_messages_resend_id", table_name="outreach_messages")
    op.drop_column("outreach_messages", "scheduled_at")
    op.drop_column("outreach_messages", "error_message")
    op.drop_column("outreach_messages", "resend_id")