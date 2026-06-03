import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USERNAME = os.getenv("DB_USERNAME", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
DB_NAME = os.getenv("DB_NAME", "speed_builder")
DB_DEFAULT_DB = os.getenv("DB_DEFAULT_DB", "postgres")
USE_SQLITE = os.getenv("USE_SQLITE", "false").lower() in {"1", "true", "yes"}


def _postgres_url(database: str) -> URL:
    return URL.create(
        drivername="postgresql+psycopg2",
        username=DB_USERNAME,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=database,
    )


def _create_postgres_engine(url: URL):
    engine = create_engine(url, echo=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        message = str(exc).lower()
        if "does not exist" in message and url.database != DB_DEFAULT_DB:
            admin_url = _postgres_url(DB_DEFAULT_DB)
            admin_engine = create_engine(admin_url, echo=True)
            try:
                with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin_conn:
                    admin_conn.execute(text(f'CREATE DATABASE "{url.database}"'))
            finally:
                admin_engine.dispose()
            engine.dispose()
            engine = create_engine(url, echo=True)
        else:
            raise
    return engine


if USE_SQLITE:
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///./{DB_NAME or 'app'}.db")
    engine = create_engine(DATABASE_URL, echo=True)
else:
    raw_url = os.getenv("DATABASE_URL")
    if raw_url:
        parsed_url = make_url(raw_url)
        if parsed_url.drivername.startswith("postgresql"):
            engine = _create_postgres_engine(parsed_url)
        else:
            engine = create_engine(raw_url, echo=True)
    else:
        engine = _create_postgres_engine(_postgres_url(DB_NAME))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency – yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
