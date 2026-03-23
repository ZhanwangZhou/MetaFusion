# expt/yfcc_subset.py
# Randomly select photo subset from yfcc100m_dataset and store to table download_queue
import sqlite3
from dataset.config import DB_PATH, overview


def create_download_queue(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS download_queue (
          photoid     INTEGER PRIMARY KEY,
          downloadurl TEXT NOT NULL,
          ext         TEXT,
          lat         REAL,
          lon         REAL,
          datetaken   TEXT,
          title       TEXT,
          description TEXT,
          usertags    TEXT,
          machinetags TEXT,
          status      INTEGER NOT NULL DEFAULT 0,
          tries       INTEGER NOT NULL DEFAULT 0,
          last_error  TEXT
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dq_status ON download_queue(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dq_time ON download_queue(datetaken);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dq_latlon ON download_queue(lat, lon);")
    conn.commit()


def delete_download_queue(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS download_queue;")
    conn.commit()


def batch_insert_to_queue(conn: sqlite3.Connection, limit: int = 200_000):
    cursor = conn.cursor()

    cursor.execute(f"""
        INSERT OR IGNORE INTO download_queue
            (photoid, downloadurl, ext, lat, lon, datetaken, title, description, usertags, machinetags)
        SELECT
            photoid,
            downloadurl,
            ext,
            CAST(latitude  AS REAL) AS lat,
            CAST(longitude AS REAL) AS lon,
            datetaken,
            title,
            description,
            usertags,
            machinetags
        FROM yfcc100m_dataset
        WHERE downloadurl IS NOT NULL AND downloadurl <> ''
          AND latitude  IS NOT NULL AND latitude  <> ''
          AND longitude IS NOT NULL AND longitude <> ''
          AND datetaken IS NOT NULL AND datetaken <> ''
          AND CAST(latitude  AS REAL) BETWEEN -90  AND 90
          AND CAST(longitude AS REAL) BETWEEN -180 AND 180
        ORDER BY RANDOM()
        LIMIT ?;
    """, (limit,))
    conn.commit()


if __name__ == '__main__':
    connection = sqlite3.connect(DB_PATH)
    delete_download_queue(connection)
    create_download_queue(connection)
    print('Table Download_queue created')
    batch_insert_to_queue(connection)
    print('Finish insertion')
    overview(connection, 'download_queue')
    connection.close()
