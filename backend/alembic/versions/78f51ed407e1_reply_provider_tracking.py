"""reply_provider_tracking

Revision ID: 78f51ed407e1
Revises: 05c0543e20d8
Create Date: 2026-05-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "78f51ed407e1"
down_revision: Union[str, None] = "05c0543e20d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("replies", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("replies", sa.Column("provider_inbound_id", sa.String(length=255), nullable=True))
    op.create_index("idx_replies_lead", "replies", ["lead_id"], unique=False)
    op.create_index("idx_replies_provider_inbound", "replies", ["provider_inbound_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_replies_provider_inbound", table_name="replies")
    op.drop_index("idx_replies_lead", table_name="replies")
    op.drop_column("replies", "provider_inbound_id")
    op.drop_column("replies", "provider")

