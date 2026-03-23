# expt/yfcc_subset_migrate.py
# Migrate metadata of successfully downloaded photos to the photo table
from pathlib import Path
from dataset.config import *


PHOTO_DIR = Path(OUT_DIR)


def compute_saved_path(photoid: int, ext: str) -> str:
    """
    Customize this based on your real storage logic.
    Example: photos/12345.jpg
    """
    ext = ext.lstrip(".") if ext else "jpg"
    return str(PHOTO_DIR / f"{photoid}.{ext}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create new table
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {PHOTO_TABLE_NAME} (
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
            vector_id   INTEGER,
            saved_path  TEXT
        );
    """)

    # Select only successfully downloaded rows
    cursor.execute("""
        SELECT photoid, downloadurl, ext, lat, lon, datetaken,
               title, description, usertags, machinetags
        FROM download_queue
        WHERE status = 1
    """)

    rows = cursor.fetchall()
    print(f"Found {len(rows)} downloaded rows")

    # Insert into new table
    insert_sql = f"""
        INSERT OR REPLACE INTO {PHOTO_TABLE_NAME} (
            photoid, downloadurl, ext, lat, lon, datetaken,
            title, description, usertags, machinetags,
            vector_id, saved_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    for row in rows:
        (photoid, downloadurl, ext, lat, lon, datetaken,
         title, description, usertags, machinetags) = row

        saved_path = compute_saved_path(photoid, ext)

        cursor.execute(insert_sql, (
            photoid, downloadurl, ext, lat, lon, datetaken,
            title, description, usertags, machinetags,
            None,           # vector_id left blank
            saved_path
        ))

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
