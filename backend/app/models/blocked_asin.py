from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func
from ..database import Base


class BlockedAsin(Base):
    __tablename__ = "blocked_asins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    asin = Column(String(16), nullable=False)
    blocked_at = Column(DateTime, server_default=func.now())
