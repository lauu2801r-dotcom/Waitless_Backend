from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

def _normalizar_url(url: str) -> str:
    """Neon/Render a veces entregan 'postgres://', que SQLAlchemy 2 ya no acepta."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


engine = create_engine(
    _normalizar_url(settings.DATABASE_URL),
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()