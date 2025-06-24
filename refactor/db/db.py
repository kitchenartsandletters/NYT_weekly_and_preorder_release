import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables for local development; no effect in Railway
load_dotenv()

# Railway injects DATABASE_INTERNAL_URL for private networking
DATABASE_URL = os.environ.get("DATABASE_INTERNAL_URL") or os.environ.get("DATABASE_URL")


def get_connection():
    """Return a new psycopg2 connection using the internal database URL."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_INTERNAL_URL is not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
