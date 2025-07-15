import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

# Prefer Railway's internal URL when present
DB_URL = os.getenv("DATABASE_INTERNAL_URL") or os.getenv("DATABASE_URL", "")


def get_connection():
    """Return a new database connection using the configured database URL."""
    if not DB_URL:
        raise RuntimeError("DATABASE_INTERNAL_URL is not set")
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)


def initialize_schema(schema_path: str) -> None:
    """Execute SQL from schema_path to create tables."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            with open(schema_path, "r", encoding="utf-8") as f:
                cur.execute(f.read())
        conn.commit()
