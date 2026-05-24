"""outreach_message_provider_fields

Revision ID: 05c0543e20d8
Revises: 2725d4eb8a75
Create Date: 2026-05-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "05c0543e20d8"
down_revision: Union[str, None] = "2725d4eb8a75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("outreach_messages", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("outreach_messages", sa.Column("provider_message_id", sa.String(length=255), nullable=True))
    op.add_column("outreach_messages", sa.Column("to_email", sa.String(length=320), nullable=True))
    op.add_column("outreach_messages", sa.Column("error", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column("outreach_messages", "error")
    op.drop_column("outreach_messages", "to_email")
    op.drop_column("outreach_messages", "provider_message_id")
    op.drop_column("outreach_messages", "provider")

