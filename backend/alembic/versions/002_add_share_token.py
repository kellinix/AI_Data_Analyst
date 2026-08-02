"""Add share_token to analyses

Revision ID: 002_add_share_token
Revises: 001_initial
Create Date: 2026-07-12 00:00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002_add_share_token"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("share_token", sa.String(64), nullable=True))
    op.create_index(
        "ix_analyses_share_token", "analyses", ["share_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_share_token", table_name="analyses")
    op.drop_column("analyses", "share_token")
