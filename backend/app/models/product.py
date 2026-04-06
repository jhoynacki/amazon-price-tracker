from sqlalchemy import Column, String, DateTime, Text, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Product(Base):
    __tablename__ = "products"

    asin = Column(String(16), primary_key=True)
    title = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    product_url = Column(Text, nullable=True)
    category = Column(String(128), nullable=True)
    brand = Column(String(128), nullable=True)

    # Latest known price (cached — authoritative data is in price_history)
    current_price = Column(Numeric(10, 2), nullable=True)
    list_price = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(8), default="USD")
    in_stock = Column(String(32), default="Unknown")

    last_checked = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user_products = relationship("UserProduct", back_populates="product")
    price_history = relationship("PriceHistory", back_populates="product",
                                 order_by="PriceHistory.checked_at.desc()")
