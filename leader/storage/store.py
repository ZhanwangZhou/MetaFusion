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


def prefilter_candidate_silos(
    start_ts=None,
    end_ts=None,
    min_lat=None,
    max_lat=None,
    min_lon=None,
    max_lon=None,
    any_tags=None,
    limit=None,
    database=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD,
    host=DB_HOST, port=DB_PORT, table='photos_meta'
):
    """
    Prefilter silos based on metadata, returning matching counts per silo:
    [(silo_id, count), ...] sorted by count descending

    Parameters:
      - start_ts, end_ts: time range (Python datetime or string accepted by psycopg2)
      - min_lat, max_lat, min_lon, max_lon: geographic bounds (optional)
      - any_tags: list[str], match if the tags array contains any of these (tags && any_tags)
      - limit: take only the top N silos (optional)
    """
    conn = psycopg2.connect(
        database=database, user=username, password=password,
        host=host, port=port
    )
    cur = conn.cursor()

    where = []
    params = {}

    if start_ts is not None:
        where.append("ts >= %(start_ts)s")
        params["start_ts"] = start_ts
    if end_ts is not None:
        where.append("ts <= %(end_ts)s")
        params["end_ts"] = end_ts

    if min_lat is not None:
        where.append("lat >= %(min_lat)s")
        params["min_lat"] = min_lat
    if max_lat is not None:
        where.append("lat <= %(max_lat)s")
        params["max_lat"] = max_lat
    if min_lon is not None:
        where.append("lon >= %(min_lon)s")
        params["min_lon"] = min_lon
    if max_lon is not None:
        where.append("lon <= %(max_lon)s")
        params["max_lon"] = max_lon

    if any_tags:
        # Match any tag: tags && ARRAY[...]
        where.append("tags && %(any_tags)s")
        params["any_tags"] = any_tags

    where_clause = ""
    if where:
        where_clause = "WHERE " + " AND ".join(where)

    sql = f"""
        SELECT silo_id, COUNT(*) AS cnt
        FROM {table}
        {where_clause}
        GROUP BY silo_id
        ORDER BY cnt DESC
    """
    if limit is not None:
        sql += " LIMIT %(limit)s"
        params["limit"] = limit

    cur.execute(sql, params)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    # rows: list[tuple[str, int]]  -> [(silo_id, count), ...]
    return rows


def search_metadata(
    start_ts=None,
    end_ts=None,
    min_lat=None,
    max_lat=None,
    min_lon=None,
    max_lon=None,
    any_tags=None,
    silo_ids=None,
    limit=1000,
    database=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD,
    host=DB_HOST, port=DB_PORT, table='photos_meta'
):
    """
    Query photos by metadata, returning:
    [ { "photo_id": ..., "silo_id": ..., "ts": ..., "lat": ..., "lon": ..., "tags": [...] }, ... ]

    This can be used for:
      - Leader to pick candidate photo_ids by metadata
      - Grouping by silo_id to send each follower the list of photo_ids they need to search
    """
    conn = psycopg2.connect(
        database=database, user=username, password=password,
        host=host, port=port
    )
    cur = conn.cursor()

    where = []
    params = {}

    if start_ts is not None:
        where.append("ts >= %(start_ts)s")
        params["start_ts"] = start_ts
    if end_ts is not None:
        where.append("ts <= %(end_ts)s")
        params["end_ts"] = end_ts

    if min_lat is not None:
        where.append("lat >= %(min_lat)s")
        params["min_lat"] = min_lat
    if max_lat is not None:
        where.append("lat <= %(max_lat)s")
        params["max_lat"] = max_lat
    if min_lon is not None:
        where.append("lon >= %(min_lon)s")
        params["min_lon"] = min_lon
    if max_lon is not None:
        where.append("lon <= %(max_lon)s")
        params["max_lon"] = max_lon

    if any_tags:
        where.append("tags && %(any_tags)s")
        params["any_tags"] = any_tags

    if silo_ids:
        # Only search in specific silos, e.g., candidate silos returned by prefilter
        where.append("silo_id = ANY(%(silo_ids)s)")
        params["silo_ids"] = silo_ids

    where_clause = ""
    if where:
        where_clause = "WHERE " + " AND ".join(where)

    sql = f"""
        SELECT photo_id, silo_id, ts, lat, lon, tags
        FROM {table}
        {where_clause}
        ORDER BY ts DESC
        LIMIT %(limit)s
    """
    params["limit"] = limit

    cur.execute(sql, params)
    rows = cur.fetchall()

    cur.close()
    conn.close()

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
