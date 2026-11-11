from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Rank(Base):
    __tablename__ = "ranks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)       -- Наприклад: "Рекрут", "Солдат"
    min_activity = Column(Numeric(12, 2), nullable=False)    -- Нижня межа
    max_activity = Column(Numeric(12, 2), nullable=False)    -- Верхня межа
    commission_rate = Column(Numeric(5, 4), nullable=False)   -- Наприклад, 0.0500 для 5%

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False)
    total_activity = Column(Numeric(12, 2), default=0.00)     -- Купівлі + продажі + донати
    current_rank = Column(String(50), default='Рекрут')
    payout_card = Column(String(30), nullable=True)           -- Картка для виплат продавцю
    created_at = Column(DateTime, server_default=func.now())

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)           -- Повна сума покупки
    commission = Column(Numeric(12, 2), nullable=False)       -- Ваша комісія маркетплейсу
    seller_payout = Column(Numeric(12, 2), nullable=False)    -- Сума до виплати продавцю
    status = Column(String(30), default='pending')            -- pending, success, failed
    created_at = Column(DateTime, server_default=func.now())