from sqlalchemy import Column, String, DateTime, Numeric, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asin = Column(String(16), ForeignKey("products.asin", ondelete="CASCADE"), nullable=False)
    price = Column(Numeric(10, 2), nullable=True)
    list_price = Column(Numeric(10, 2), nullable=True)
    discount_pct = Column(Numeric(5, 2), nullable=True)
    deal_badge = Column(String(128), nullable=True)   # "Deal of the Day", "Lightning Deal", etc.
    in_stock = Column(String(32), nullable=True)
    source = Column(String(16), default="paapi")      # "paapi" | "scraper"
    checked_at = Column(DateTime, server_default=func.now(), index=True)

    product = relationship("Product", back_populates="price_history")
