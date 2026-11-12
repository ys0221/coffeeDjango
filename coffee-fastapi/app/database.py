"""DB 설정 — Spring의 application.yml(datasource) + EntityManager 역할.

- engine        : DataSource
- SessionLocal  : EntityManager/영속성 컨텍스트 팩토리
- get_db()      : 요청마다 세션을 열고 닫는 의존성 (≈ @Transactional 범위)
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./coffee.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
