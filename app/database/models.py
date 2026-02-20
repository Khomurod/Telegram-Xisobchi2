from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone, timedelta

Base = declarative_base()

# Uzbekistan timezone (UTC+5)
UZT = timezone(timedelta(hours=5))


def now_uzt():
    """Current time in Uzbekistan timezone."""
    return datetime.now(UZT)


class User(Base):
    """Telegram user record. Isolated per Telegram ID."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    first_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now_uzt)

    transactions = relationship("Transaction", back_populates="user", lazy="selectin")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id})>"


class Transaction(Base):
    """Financial transaction linked to a user."""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(10), nullable=False)  # "income" or "expense"
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="UZS")
    category = Column(String(100), nullable=False, default="boshqa")
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=now_uzt)

    user = relationship("User", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, type={self.type}, amount={self.amount} {self.currency})>"
