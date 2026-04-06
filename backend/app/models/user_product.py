from sqlalchemy import Column, String, DateTime, Numeric, Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class UserProduct(Base):
    __tablename__ = "user_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    asin = Column(String(16), ForeignKey("products.asin", ondelete="CASCADE"), nullable=False)

    # Alert thresholds — at least one should be set
    target_price = Column(Numeric(10, 2), nullable=True)    # Alert if price <= this
    target_discount_pct = Column(Numeric(5, 2), nullable=True)  # Alert if discount >= this %

    # Per-user alert channel overrides (falls back to user defaults if null)
    notify_email = Column(Boolean, default=True)
    notify_sms = Column(Boolean, default=False)
    notify_telegram = Column(Boolean, default=False)
    notify_pushover = Column(Boolean, default=False)

    # Source: "import" (from CSV) | "manual" (user added)
    source = Column(String(32), default="manual")

    # Last alert sent (to avoid repeat alerts)
    last_alert_price = Column(Numeric(10, 2), nullable=True)
    last_alert_at = Column(DateTime, nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="products")
    product = relationship("Product", back_populates="user_products")
