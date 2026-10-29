"""Remember an open Stripe checkout session per account."""

import sqlalchemy as sa

from alembic import op

revision = "008_billing_checkout_session"
down_revision = "007_usage_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions", sa.Column("pending_checkout_session_id", sa.String(128), nullable=True)
    )
    op.add_column(
        "subscriptions", sa.Column("checkout_expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "checkout_expires_at")
    op.drop_column("subscriptions", "pending_checkout_session_id")
