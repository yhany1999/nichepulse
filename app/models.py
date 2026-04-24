import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

DEFAULT_KEYWORDS = [
    "AI automation",
    "n8n workflow automation",
    "Claude code AI",
    "MCP model context protocol",
    "n8n Claude",
    "AI agent workflow",
]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    keywords = Column(JSON, default=lambda: list(DEFAULT_KEYWORDS))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    subscription = relationship("Subscription", back_populates="user", uselist=False)

    @property
    def is_subscribed(self):
        return self.subscription is not None and self.subscription.status == "active"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    stripe_customer_id = Column(String, unique=True, nullable=True)
    stripe_subscription_id = Column(String, unique=True, nullable=True)
    status = Column(String, default="inactive")  # inactive | active | past_due | cancelled
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    period_end = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="subscription")
