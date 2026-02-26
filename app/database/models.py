from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from app.constants import UZT

Base = declarative_base()




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
    phone_number = Column(String(20), nullable=True)
    telegram_first_name = Column(String(255), nullable=True)  # Telegram profile name (separate from typed name)
    city = Column(String(50), nullable=True)  # Ramadan feature — Aladhan API city key
    created_at = Column(DateTime(timezone=True), default=now_uzt)

    transactions = relationship("Transaction", back_populates="user", lazy="selectin", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id})>"


class Transaction(Base):
    """Financial transaction linked to a user."""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(10), nullable=False)  # "income" or "expense"
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="UZS")
    category = Column(String(100), nullable=False, default="boshqa")
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_uzt)

    user = relationship("User", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, type={self.type}, amount={self.amount} {self.currency})>"
