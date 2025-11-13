# leader/storage/store.py  (or leader/storage/db.py)
import psycopg2
from psycopg2.extras import register_default_jsonb
from utils.config import *


def init_metadata_table(
        database=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT, table='photos_meta'
):
    """
    Initialize the global metadata table in PostgreSQL.
    """
    register_default_jsonb(loads=None)
    conn = psycopg2.connect(
        database=database, user=username, password=password,
        host=host, port=port
    )
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            photo_id   TEXT PRIMARY KEY,
            silo_id    TEXT NOT NULL,
            ts         TIMESTAMPTZ,
            lat        DOUBLE PRECISION,
            lon        DOUBLE PRECISION,
            tags       TEXT[] DEFAULT '{{}}',
            extra      JSONB  DEFAULT '{{}}'::jsonb
        );
    """)

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_silo_ts ON {table}(silo_id, ts);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_tags ON {table} USING GIN(tags);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_lat_lon ON {table}(lat, lon);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_ts ON {table}(ts);")

    cur.close()
    conn.close()
