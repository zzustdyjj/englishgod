from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{config.DB_PATH}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db():
    from . import models  # noqa: F401  注册所有表

    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
