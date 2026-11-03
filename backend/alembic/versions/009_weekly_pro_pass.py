"""Store one-time seven-day Pro payments and their expiry."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "009_weekly_pro_pass"
down_revision = "008_billing_checkout_session"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pro_pass_expires_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("billing_livemode", sa.Boolean()))
    op.add_column("subscriptions", sa.Column("stripe_livemode", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("subscriptions", sa.Column("pending_checkout_offer", sa.String(16)))
    # All billing deployed before this migration was verified Stripe sandbox.
    # Tag that entitlement so promoting this same site cannot grant live Pro
    # from an earlier test payment, or reuse a test customer with a live key.
    op.execute("UPDATE users SET billing_livemode = false WHERE plan = 'starter' "
               "AND id IN (SELECT user_id FROM subscriptions WHERE stripe_customer_id IS NOT NULL)")
    op.create_table(
        "pro_passes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stripe_checkout_session_id", sa.String(128), nullable=False, unique=True),
        sa.Column("stripe_payment_intent_id", sa.String(128), nullable=False, unique=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pro_passes_user_id", "pro_passes", ["user_id"])


def downgrade() -> None:
    op.drop_table("pro_passes")
    op.drop_column("subscriptions", "pending_checkout_offer")
    op.drop_column("subscriptions", "stripe_livemode")
    op.drop_column("users", "billing_livemode")
    op.drop_column("users", "pro_pass_expires_at")
