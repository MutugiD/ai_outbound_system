"""add whatsapp_sessions table

Revision ID: a1b2c3d4e5f6
Revises: 7b1bfbea3bda
Create Date: 2026-05-28 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "7b1bfbea3bda"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("team_id", sa.String(36), nullable=False),
        sa.Column("instance_name", sa.String(length=100), nullable=False),
        sa.Column("phone_number", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="disconnected"),
        sa.Column("qr_code", sa.Text(), nullable=True),
        sa.Column("paired_at", sa.DateTime(), nullable=True),
        sa.Column("last_ping", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_name"),
    )
    op.create_index("idx_wa_sessions_team", "whatsapp_sessions", ["team_id"])
    op.create_index("idx_wa_sessions_status", "whatsapp_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("idx_wa_sessions_status")
    op.drop_index("idx_wa_sessions_team")
    op.drop_table("whatsapp_sessions")