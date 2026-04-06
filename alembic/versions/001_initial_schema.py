"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("encrypted_email", sa.Text, nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("encrypted_access_token", sa.Text, nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text, nullable=True),
        sa.Column("token_expires_at", sa.DateTime, nullable=True),
        sa.Column("alert_email", sa.String(255), nullable=True),
        sa.Column("alert_sms", sa.String(30), nullable=True),
        sa.Column("alert_telegram_chat_id", sa.String(64), nullable=True),
        sa.Column("alert_pushover_user_key", sa.String(64), nullable=True),
        sa.Column("alerts_enabled", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )

    op.create_table(
        "products",
        sa.Column("asin", sa.String(16), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("product_url", sa.Text, nullable=True),
        sa.Column("category", sa.String(128), nullable=True),
        sa.Column("brand", sa.String(128), nullable=True),
        sa.Column("current_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("list_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(8), default="USD"),
        sa.Column("in_stock", sa.String(32), default="Unknown"),
        sa.Column("last_checked", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "user_products",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asin", sa.String(16), sa.ForeignKey("products.asin", ondelete="CASCADE"), nullable=False),
        sa.Column("target_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("target_discount_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("notify_email", sa.Boolean, default=True),
        sa.Column("notify_sms", sa.Boolean, default=False),
        sa.Column("notify_telegram", sa.Boolean, default=False),
        sa.Column("notify_pushover", sa.Boolean, default=False),
        sa.Column("source", sa.String(32), default="manual"),
        sa.Column("last_alert_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("last_alert_at", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_user_product", "user_products", ["user_id", "asin"])

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("asin", sa.String(16), sa.ForeignKey("products.asin", ondelete="CASCADE"), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("list_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("discount_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("deal_badge", sa.String(128), nullable=True),
        sa.Column("in_stock", sa.String(32), nullable=True),
        sa.Column("source", sa.String(16), default="paapi"),
        sa.Column("checked_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_price_history_asin_checked_at", "price_history", ["asin", "checked_at"])


def downgrade():
    op.drop_table("price_history")
    op.drop_table("user_products")
    op.drop_table("products")
    op.drop_table("users")
