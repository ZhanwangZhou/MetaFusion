# leader/storage/store.py
import psycopg2
from datetime import datetime
from psycopg2.extras import register_default_jsonb
from utils.config import *


def init_metadata_table(
        database=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT, table=DB_LEADER_TABLE_NAME
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
            photo_id    TEXT PRIMARY KEY,
            silo_id     INTEGER NOT NULL,
            photo_name  TEXT,
            ts          TIMESTAMPTZ,
            lat         DOUBLE PRECISION,
            lon         DOUBLE PRECISION,
            cam_make    TEXT,
            cam_model   TEXT,
            tags        TEXT[] DEFAULT '{{}}',
            extra       JSONB  DEFAULT '{{}}'::jsonb
        );
    """)

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_silo_ts ON {table}(silo_id, ts);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_tags ON {table} USING GIN(tags);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_lat_lon ON {table}(lat, lon);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_ts ON {table}(ts);")

    cur.close()
    return conn


def insert_new_photo(conn, silo_id, metadata, table=DB_LEADER_TABLE_NAME):
    cur = conn.cursor()
    timestamp = metadata.get('timestamp')
    if timestamp:
        timestamp = datetime.strptime(timestamp, "%Y:%m:%d %H:%M:%S")
    cur.execute(
        f"""
        INSERT INTO {table}
        (photo_id, silo_id, photo_name, ts, lat, lon, cam_make, cam_model, tags, extra)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            metadata.get('photo_id'),
            silo_id,
            metadata.get('photo_name'),
            timestamp,
            metadata.get('latitude'),
            metadata.get('longitude'),
            metadata.get('camera_make'),
            metadata.get('camera_model'),
            None,
            None,
        )
    )
    cur.close()


def clear_all_photos(conn, table='photos_meta'):
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table}')
    cur.close()


def query_by_photo_id(conn, photo_id, table=DB_LEADER_TABLE_NAME):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT photo_id FROM {table}
        WHERE photo_id = '{photo_id}'
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def query_photo_num(conn, table=DB_LEADER_TABLE_NAME):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT COUNT(DISTINCT photo_id) FROM {table}
    """)
    row = cur.fetchone()
    cur.close()
    return row


def prefilter_candidate_silos(conn, metadata, limit=None, table=DB_LEADER_TABLE_NAME):
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


def fetch_photos_by_metadata(conn, metadata, silo_ids, limit=1000,
                             table=DB_LEADER_TABLE_NAME):
    """
    Query photos by metadata, returning:
    [ { "photo_id": ..., "silo_id": ..., "ts": ..., "lat": ..., "lon": ..., "tags": [...] }, ... ]

    This can be used for:
      - Leader to pick candidate photo_ids by metadata
      - Grouping by silo_id to send each follower the list of photo_ids they need to search
    """
    cur = conn.cursor()

    sql = f"""
        SELECT photo_id, silo_id, photo_name, ts, lat, lon, cam_make, cam_model, tags
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
    for photo_id, silo_id, photo_name, ts, lat, lon, cam_make, cam_model, tags in rows:
        results.append({
            "photo_id": photo_id,
            "silo_id": silo_id,
            "photo_name": photo_name,
            "ts": ts,
            "lat": lat,
            "lon": lon,
            "cam_make": cam_make,
            "cam_model": cam_model,
            "tags": tags,
        })
    return results
