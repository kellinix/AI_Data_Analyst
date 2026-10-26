"""Add operational usage events and conservatively backfill existing work."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "007_usage_events"
down_revision: str | None = "006_dashboard_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.UniqueConstraint("kind", "resource_id", name="uq_usage_event_resource"),
        sa.CheckConstraint("kind IN ('analysis', 'ai_followup')", name="ck_usage_event_kind"),
        sa.CheckConstraint("status IN ('reserved', 'completed', 'failed', 'legacy_unknown')", name="ck_usage_event_status"),
    )
    op.create_index("ix_usage_events_user_occurred", "usage_events", ["user_id", "occurred_at"])
    op.execute(sa.text("""
        INSERT INTO usage_events (id, user_id, kind, resource_id, status, source, occurred_at, completed_at)
        SELECT gen_random_uuid(), user_id, 'analysis', id,
               CASE WHEN status = 'completed' THEN 'completed'
                    WHEN status = 'failed' THEN 'failed' ELSE 'reserved' END,
               'backfill', created_at, completed_at
        FROM analyses
    """))
    op.execute(sa.text("""
        INSERT INTO usage_events
          (id, user_id, kind, resource_id, status, source, occurred_at, completed_at,
           model, prompt_tokens, completion_tokens)
        SELECT gen_random_uuid(), a.user_id, 'ai_followup', m.id,
               CASE WHEN m.internal_metadata ->> 'status' = 'failed' THEN 'failed'
                    WHEN m.internal_metadata ->> 'status' = 'succeeded'
                      OR m.internal_metadata ? 'prompt_tokens' THEN 'completed'
                    ELSE 'legacy_unknown' END,
               'backfill', m.created_at, m.created_at,
               LEFT(m.internal_metadata ->> 'model', 128),
               CASE WHEN (m.internal_metadata ->> 'prompt_tokens') ~ '^[0-9]{1,9}$'
                    THEN (m.internal_metadata ->> 'prompt_tokens')::integer ELSE NULL END,
               CASE WHEN (m.internal_metadata ->> 'completion_tokens') ~ '^[0-9]{1,9}$'
                    THEN (m.internal_metadata ->> 'completion_tokens')::integer ELSE NULL END
        FROM chat_messages AS m
        JOIN chat_sessions AS s ON s.id = m.session_id
        JOIN analyses AS a ON a.id = s.analysis_id
        WHERE m.role = 'assistant'
    """))


def downgrade() -> None:
    op.drop_table("usage_events")
