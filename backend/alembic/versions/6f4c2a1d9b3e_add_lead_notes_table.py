"""add lead_notes table

Revision ID: 6f4c2a1d9b3e
Revises: e46e530b6def
Create Date: 2026-05-24

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision = "6f4c2a1d9b3e"
down_revision = "e46e530b6def"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("note_type", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_lead_notes_lead", "lead_notes", ["lead_id"])
    op.create_index("idx_lead_notes_user", "lead_notes", ["user_id"])
    op.create_index("idx_lead_notes_created", "lead_notes", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_lead_notes_created", table_name="lead_notes")
    op.drop_index("idx_lead_notes_user", table_name="lead_notes")
    op.drop_index("idx_lead_notes_lead", table_name="lead_notes")
    op.drop_table("lead_notes")
