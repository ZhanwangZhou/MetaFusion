# expt/yfcc_photo_download.py
# Download photo files from urls in table download_queue
import os
import sqlite3
import time
import random
from typing import Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataset.config import DB_PATH, OUT_DIR
import requests


BATCH_SIZE = 2000               # how many rows to fetch from sqlite per batch
WORKERS = 64                    # concurrent downloads
MAX_TRIES = 3
TIMEOUT = (5, 30)


def out_path(photoid: int, ext: Optional[str]) -> str:
    ext = (ext or "jpg").lstrip(".")
    return os.path.join(OUT_DIR, f"{photoid}.{ext}")


def download_one(photoid: int, url: str, ext: Optional[str]) -> Tuple[int, int, str]:
    """
    Returns: (photoid, status, error_message)
      status: 1 ok, -1 failed
    """
    path = out_path(photoid, ext)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return photoid, 1, ""

    try:
        with requests.get(url, stream=True, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}) as r:
            if r.status_code != 200:
                return photoid, -1, f"HTTP {r.status_code}"

            tmp = path + ".part"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            os.replace(tmp, path)
        return photoid, 1, ""
    except Exception as e:
        return photoid, -1, repr(e)


def fetch_batch(conn: sqlite3.Connection) -> List[Tuple[int, str, Optional[str], int]]:
    """
    Fetch pending rows. We also fetch tries so we can stop retrying after MAX_TRIES.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT photoid, downloadurl, ext, tries
        FROM download_queue
        WHERE status = 0 AND tries < ?
        LIMIT ?
        """,
        (MAX_TRIES, BATCH_SIZE),
    )
    return cur.fetchall()


def mark_increase_tries(conn: sqlite3.Connection, photoids: List[int]) -> None:
    """
    Claim rows for this batch by incrementing tries.
    (Prevents infinite loops and helps resume.)
    """
    cur = conn.cursor()
    cur.executemany(
        "UPDATE download_queue SET tries = tries + 1 WHERE photoid = ?",
        [(pid,) for pid in photoids],
    )
    conn.commit()


def update_results(conn: sqlite3.Connection, results: List[Tuple[int, int, str]]) -> None:
    cur = conn.cursor()
    cur.executemany(
        """
        UPDATE download_queue
        SET status = ?, last_error = ?
        WHERE photoid = ?
        """,
        [(status, err, pid) for (pid, status, err) in results],
    )
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    total_ok = 0
    total_fail = 0

    while True:
        batch = fetch_batch(conn)
        if not batch:
            break

        photoids = [row[0] for row in batch]
        mark_increase_tries(conn, photoids)

        # Download concurrently
        results: List[Tuple[int, int, str]] = []
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = {
                ex.submit(download_one, photoid, url, ext): photoid
                for (photoid, url, ext, tries) in batch
            }
            for fut in as_completed(futures):
                results.append(fut.result())

        # Update DB
        update_results(conn, results)

        ok = sum(1 for (_, status, _) in results if status == 1)
        fail = len(results) - ok
        total_ok += ok
        total_fail += fail

        print(f"batch done: ok={ok}, fail={fail}, total_ok={total_ok}, total_fail={total_fail}")

        # small jitter to be polite / reduce throttling bursts
        time.sleep(0.2 + random.random() * 0.3)

    # Mark remaining as failed if they hit MAX_TRIES
    conn.execute("UPDATE download_queue SET status = -1 WHERE status = 0 AND tries >= ?", (MAX_TRIES,))
    conn.commit()

    # Summary
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM download_queue WHERE status = 1")
    ok_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM download_queue WHERE status = -1")
    fail_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM download_queue WHERE status = 0")
    pending_count = cur.fetchone()[0]

    print(f"FINAL: ok={ok_count}, fail={fail_count}, pending={pending_count}")
    conn.close()


if __name__ == '__main__':
    main()
