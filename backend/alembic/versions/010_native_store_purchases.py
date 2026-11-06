"""Add native store purchase ownership and isolated purchase reservations."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "010_native_store_purchases"
down_revision = "009_weekly_pro_pass"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("store_access_expires_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("store_purchase_pending_until", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("store_purchase_intent", sa.String(36)))
    op.create_table("store_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("owner_hash", sa.String(64), nullable=False),
        sa.Column("store", sa.String(16), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("purchase_key", sa.String(128), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=False),
        sa.Column("offer", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("encrypted_token", sa.Text()),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("store", "environment", "purchase_key", name="uq_store_purchase_identity"))
    op.create_index("ix_store_purchases_user_id", "store_purchases", ["user_id"])


def downgrade():
    op.drop_table("store_purchases")
    op.drop_column("users", "store_purchase_intent")
    op.drop_column("users", "store_purchase_pending_until")
    op.drop_column("users", "store_access_expires_at")
