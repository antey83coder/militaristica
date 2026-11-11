from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models import Base  # Імпортуємо моделі з models.py

# Замініть на ваші реальні дані доступу до бази PostgreSQL
DATABASE_URL = "postgresql+asyncpg://user:password@localhost/militaristica_db"

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Функція для створення таблиць у базі даних
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Функція-залежність (Dependency) для отримання сесії БД у роутерах
async def get_db():
    async with async_session() as session:
        yield session