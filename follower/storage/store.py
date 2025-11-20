# follower/storage/store.py
import psycopg2
from psycopg2.extras import register_default_jsonb
from utils.config import *


def init_vector_table(
        database=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT, table=DB_FOLLOWER_TABLE_NAME
):
    """
    Initialize the vector-photo mapping table in PostgresSQL.
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
            vector_id       INTEGER PRIMARY KEY,
            photo_id        TEXT NOT NULL,
            photo_name      TEXT,
            photo_format    TEXT,
            saved_path      TEXT
        );
    """)
    cur.close()
    return conn


def clear_all(conn, table=DB_FOLLOWER_TABLE_NAME):
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table}')
    cur.close()


def insert_new_photo_vector(conn, data: dict, table=DB_FOLLOWER_TABLE_NAME):
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO {table} (vector_id, photo_id, photo_name, photo_format, saved_path)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            data.get('vector_id'),
            data.get('photo_id'),
            data.get('photo_name'),
            data.get('photo_format'),
            data.get('saved_path')
        )
    )
    cur.close()


def query_by_vector_id(conn, vector_id, table=DB_FOLLOWER_TABLE_NAME):
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT * FROM {table}
        WHERE vector_id = {vector_id}
        """
    )
    row = cur.fetchone()
    cur.close()
    return row
