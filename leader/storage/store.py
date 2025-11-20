# leader/storage/store.py  (or leader/storage/db.py)
import psycopg2
from datetime import datetime
from psycopg2.extras import register_default_jsonb
from utils.config import *


def init_metadata_table(
        database=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT, table='photos_meta'
):
    """
    Initialize the global metadata table in PostgreSQL.
    TODO: adapt more metadata type. E.g. photo original name, camera model
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
    return conn


def insert_new_photo(conn, silo_id, metadata, table='photos_meta'):
    cur = conn.cursor()
    timestamp = metadata.get('timestamp')
    if timestamp:
        timestamp = datetime.strptime(timestamp, "%Y:%m:%d %H:%M:%S")
    cur.execute(
        f"""
        INSERT INTO {table} (photo_id, silo_id, ts, lat, lon, tags, extra)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            metadata.get('photo_id'),
            silo_id,
            timestamp,
            metadata.get('latitude'),
            metadata.get('longitude'),
            None,
            None,
        )
    )
    cur.close()


def clear_all_photos(conn, table='photos_meta'):
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table}')
    cur.close()


def prefilter_candidate_silos(conn, metadata, limit=None, table='photos_meta'):
    """
    Prefilter silos based on metadata, returning matching counts per silo:
    [(silo_id, count), ...] sorted by count descending
    """
    cur = conn.cursor()

    sql = f"""
        SELECT silo_id, COUNT(*) AS cnt
        FROM {table}
        WHERE (ts IS NULL OR ts >= %(start_ts)s AND ts <= %(end_ts)s)
            AND (lat IS NULL OR lat >= %(min_lat)s AND lat <= %(max_lat)s)
            AND (lon IS NULL OR lon >= %(min_lon)s AND lon <= %(max_lon)s)
        GROUP BY silo_id
        ORDER BY cnt DESC
    """

    if limit is not None:
        sql += " LIMIT %(limit)s"
        metadata["limit"] = limit

    cur.execute(sql, metadata)
    rows = cur.fetchall()
    cur.close()
    return rows


def fetch_photos_by_metadata(conn, metadata, silo_ids, limit=1000, table='photos_meta'):
    """
    Query photos by metadata, returning:
    [ { "photo_id": ..., "silo_id": ..., "ts": ..., "lat": ..., "lon": ..., "tags": [...] }, ... ]

    This can be used for:
      - Leader to pick candidate photo_ids by metadata
      - Grouping by silo_id to send each follower the list of photo_ids they need to search
    """
    cur = conn.cursor()

    sql = f"""
        SELECT photo_id, silo_id, ts, lat, lon, tags
        FROM {table}
        WHERE (ts IS NULL OR ts >= %(start_ts)s AND ts <= %(end_ts)s)
            AND (lat IS NULL OR lat >= %(min_lat)s AND lat <= %(max_lat)s)
            AND (lon IS NULL OR lon >= %(min_lon)s AND lon <= %(max_lon)s)
            AND silo_id = ANY(%(silo_ids)s)
        ORDER BY ts DESC
        LIMIT %(limit)s
    """

    metadata["limit"] = limit
    metadata["silo_ids"] = silo_ids

    cur.execute(sql, metadata)
    rows = cur.fetchall()
    cur.close()

    # Convert to a list of dicts for easier grouping by silo later
    results = []
    for photo_id, silo_id, ts, lat, lon, tags in rows:
        results.append({
            "photo_id": photo_id,
            "silo_id": silo_id,
            "ts": ts,
            "lat": lat,
            "lon": lon,
            "tags": tags,
        })
    return results
