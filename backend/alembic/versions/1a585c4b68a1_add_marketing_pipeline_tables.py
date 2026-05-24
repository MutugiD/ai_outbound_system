"""add marketing pipeline tables (audience scans/signals/drafts/usage)

Revision ID: 1a585c4b68a1
Revises: 6f4c2a1d9b3e
Create Date: 2026-05-24

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision = "1a585c4b68a1"
down_revision = "6f4c2a1d9b3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audience_scan_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("found_count", sa.Integer(), nullable=False),
        sa.Column("kept_count", sa.Integer(), nullable=False),
        sa.Column("deduped_count", sa.Integer(), nullable=False),
        sa.Column("stop_reason", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audience_scan_jobs_team_status", "audience_scan_jobs", ["team_id", "status"])
    op.create_index("idx_audience_scan_jobs_created_at", "audience_scan_jobs", ["created_at"])

    op.create_table(
        "audience_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column("source_url", sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=False),
        sa.Column("external_id", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
        sa.Column("body_excerpt", sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=True),
        sa.Column("author", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("community", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("engagement", sa.Integer(), nullable=True),
        sa.Column("matched_keywords", sa.JSON(), nullable=False),
        sa.Column("intent_label", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_audience_signals_team_platform_url",
        "audience_signals",
        ["team_id", "platform", "source_url"],
        unique=True,
    )
    op.create_index("idx_audience_signals_team_created_at", "audience_signals", ["team_id", "created_at"])
    op.create_index("ix_audience_signals_team_id", "audience_signals", ["team_id"])
    op.create_index("ix_audience_signals_platform", "audience_signals", ["platform"])

    op.create_table(
        "marketing_usage_daily",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("scans_requested", sa.Integer(), nullable=False),
        sa.Column("scans_completed", sa.Integer(), nullable=False),
        sa.Column("signals_saved", sa.Integer(), nullable=False),
        sa.Column("drafts_generated", sa.Integer(), nullable=False),
        sa.Column("llm_tokens_used", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_marketing_usage_daily_team_day", "marketing_usage_daily", ["team_id", "day"], unique=True)
    op.create_index("ix_marketing_usage_daily_team_id", "marketing_usage_daily", ["team_id"])
    op.create_index("ix_marketing_usage_daily_day", "marketing_usage_daily", ["day"])

    op.create_table(
        "social_post_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column("goal", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column("audience_signal_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("variant", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["audience_signal_id"], ["audience_signals.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_social_post_drafts_team_created_at", "social_post_drafts", ["team_id", "created_at"])
    op.create_index("ix_social_post_drafts_team_id", "social_post_drafts", ["team_id"])
    op.create_index("ix_social_post_drafts_platform", "social_post_drafts", ["platform"])


def downgrade() -> None:
    op.drop_index("ix_social_post_drafts_platform", table_name="social_post_drafts")
    op.drop_index("ix_social_post_drafts_team_id", table_name="social_post_drafts")
    op.drop_index("idx_social_post_drafts_team_created_at", table_name="social_post_drafts")
    op.drop_table("social_post_drafts")

    op.drop_index("ix_marketing_usage_daily_day", table_name="marketing_usage_daily")
    op.drop_index("ix_marketing_usage_daily_team_id", table_name="marketing_usage_daily")
    op.drop_index("uq_marketing_usage_daily_team_day", table_name="marketing_usage_daily")
    op.drop_table("marketing_usage_daily")

    op.drop_index("ix_audience_signals_platform", table_name="audience_signals")
    op.drop_index("ix_audience_signals_team_id", table_name="audience_signals")
    op.drop_index("idx_audience_signals_team_created_at", table_name="audience_signals")
    op.drop_index("uq_audience_signals_team_platform_url", table_name="audience_signals")
    op.drop_table("audience_signals")

    op.drop_index("idx_audience_scan_jobs_created_at", table_name="audience_scan_jobs")
    op.drop_index("idx_audience_scan_jobs_team_status", table_name="audience_scan_jobs")
    op.drop_table("audience_scan_jobs")
