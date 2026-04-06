"""Add blocked_asins table

Revision ID: 002
Revises: 001
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "blocked_asins",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asin", sa.String(16), nullable=False),
        sa.Column("blocked_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_blocked_user_asin", "blocked_asins", ["user_id", "asin"])


def downgrade():
    op.drop_table("blocked_asins")
