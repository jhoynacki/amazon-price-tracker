from sqlalchemy import Column, String, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)          # Amazon user_id
    encrypted_email = Column(Text, nullable=True)      # AES-encrypted
    name = Column(String(255), nullable=True)
    postal_code = Column(String(20), nullable=True)

    # Encrypted Amazon OAuth tokens
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)

    # Alert preferences
    alert_email = Column(String(255), nullable=True)
    alert_sms = Column(String(30), nullable=True)
    alert_telegram_chat_id = Column(String(64), nullable=True)
    alert_pushover_user_key = Column(String(64), nullable=True)
    alerts_enabled = Column(Boolean, default=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    products = relationship("UserProduct", back_populates="user", cascade="all, delete-orphan")
