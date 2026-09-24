import sqlite3
import json

from datetime import datetime
from app_paths import DATABASE_PATH, ensure_data_dir


def get_connection():
    ensure_data_dir()

    return sqlite3.connect(
        DATABASE_PATH
    )


def init_database():

    with get_connection() as conn:

        # User data
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_data (
                appid INTEGER PRIMARY KEY,
                status TEXT,
                notes TEXT DEFAULT ''
            )
        """)

        # Metadata retrieved from Steam
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_metadata (
                appid INTEGER PRIMARY KEY,

                genres TEXT,
                categories TEXT,

                developers TEXT,
                publishers TEXT,

                review_score INTEGER,
                review_description TEXT,
                positive_percentage REAL,
                total_reviews INTEGER,

                fetched_at TEXT
            )
        """)

        # Persistent status for metadata fetch failures/retries.
        # Successful games do not need a row here.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata_fetch_status (
                appid INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_failure_at TEXT,
                next_retry_at TEXT,
                last_error TEXT
            )
        """)

        # Migrate the old experimental label to the more accurate state name.
        conn.execute("""
            UPDATE metadata_fetch_status
            SET state = 'metadata_unavailable'
            WHERE state = 'possibly_delisted'
               OR last_error = 'store_unavailable'
        """)

def get_all_game_data():

    with get_connection() as conn:

        cursor = conn.execute("""
            SELECT
                appid,
                status,
                notes
            FROM game_data
        """)

        rows = cursor.fetchall()

    return {
        appid: {
            "status": status,
            "notes": notes or ""
        }

        for appid, status, notes in rows
    }


def save_game_data(
    appid,
    status,
    notes=""
):

    with get_connection() as conn:

        conn.execute("""
            INSERT INTO game_data (
                appid,
                status,
                notes
            )

            VALUES (?, ?, ?)

            ON CONFLICT(appid)

            DO UPDATE SET
                status = excluded.status,
                notes = excluded.notes
        """, (
            appid,
            status,
            notes
        ))


def import_game_data(games):

    rows = []

    for game in games:

        rows.append((
            int(game["appid"]),
            game["status"],
            game.get(
                "notes",
                ""
            )
        ))

    with get_connection() as conn:

        conn.executemany("""
            INSERT INTO game_data (
                appid,
                status,
                notes
            )

            VALUES (?, ?, ?)

            ON CONFLICT(appid)

            DO UPDATE SET
                status = excluded.status,
                notes = excluded.notes
        """, rows)

    return len(rows)


def get_game_metadata(appid):

    with get_connection() as conn:

        cursor = conn.execute("""
            SELECT
                genres,
                categories,
                developers,
                publishers,
                review_score,
                review_description,
                positive_percentage,
                total_reviews,
                fetched_at

            FROM game_metadata

            WHERE appid = ?
        """, (
            appid,
        ))

        row = cursor.fetchone()

    if row is None:
        return None

    return {
        "appid": appid,

        "genres": json.loads(
            row[0] or "[]"
        ),

        "categories": json.loads(
            row[1] or "[]"
        ),

        "developers": json.loads(
            row[2] or "[]"
        ),

        "publishers": json.loads(
            row[3] or "[]"
        ),

        "review_score": row[4],

        "review_description": row[5],

        "positive_percentage": row[6],

        "total_reviews": row[7],

        "fetched_at": row[8],
    }


def get_all_game_metadata():
    """
    Return all Steam metadata currently stored in the local cache.

    The result is keyed by AppID so callers such as Smart Pick can
    match an entire library against cached metadata without making
    one database query per game (and, importantly, without triggering
    any Steam requests).
    """

    with get_connection() as conn:

        cursor = conn.execute("""
            SELECT
                appid,
                genres,
                categories,
                developers,
                publishers,
                review_score,
                review_description,
                positive_percentage,
                total_reviews,
                fetched_at

            FROM game_metadata
        """)

        rows = cursor.fetchall()

    return {
        int(row[0]): {
            "appid": int(row[0]),
            "genres": json.loads(row[1] or "[]"),
            "categories": json.loads(row[2] or "[]"),
            "developers": json.loads(row[3] or "[]"),
            "publishers": json.loads(row[4] or "[]"),
            "review_score": row[5],
            "review_description": row[6],
            "positive_percentage": row[7],
            "total_reviews": row[8],
            "fetched_at": row[9],
        }
        for row in rows
    }


def save_game_metadata(metadata):

    reviews = (
        metadata.get("reviews")
        or {}
    )

    with get_connection() as conn:

        conn.execute("""
            INSERT INTO game_metadata (
                appid,
                genres,
                categories,
                developers,
                publishers,
                review_score,
                review_description,
                positive_percentage,
                total_reviews,
                fetched_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(appid)

            DO UPDATE SET
                genres = excluded.genres,
                categories = excluded.categories,
                developers = excluded.developers,
                publishers = excluded.publishers,
                review_score = excluded.review_score,
                review_description = excluded.review_description,
                positive_percentage = excluded.positive_percentage,
                total_reviews = excluded.total_reviews,
                fetched_at = excluded.fetched_at
        """, (
            int(
                metadata["appid"]
            ),

            json.dumps(
                metadata.get(
                    "genres",
                    []
                )
            ),

            json.dumps(
                metadata.get(
                    "categories",
                    []
                )
            ),

            json.dumps(
                metadata.get(
                    "developers",
                    []
                )
            ),

            json.dumps(
                metadata.get(
                    "publishers",
                    []
                )
            ),

            reviews.get(
                "review_score"
            ),

            reviews.get(
                "review_description"
            ),

            reviews.get(
                "positive_percentage"
            ),

            reviews.get(
                "total_reviews"
            ),

            datetime.now().isoformat(
                timespec="seconds"
            )
        ))

def get_metadata_fetch_status(appid):
    """Return the persistent metadata fetch state for one AppID."""

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                state,
                failure_count,
                last_failure_at,
                next_retry_at,
                last_error
            FROM metadata_fetch_status
            WHERE appid = ?
            """,
            (int(appid),),
        ).fetchone()

    if row is None:
        return None

    return {
        "appid": int(appid),
        "state": row[0],
        "failure_count": int(row[1] or 0),
        "last_failure_at": row[2],
        "next_retry_at": row[3],
        "last_error": row[4],
    }


def get_all_metadata_fetch_statuses():
    """Return all persistent metadata fetch states, keyed by AppID."""

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                appid,
                state,
                failure_count,
                last_failure_at,
                next_retry_at,
                last_error
            FROM metadata_fetch_status
            """
        ).fetchall()

    return {
        int(row[0]): {
            "appid": int(row[0]),
            "state": row[1],
            "failure_count": int(row[2] or 0),
            "last_failure_at": row[3],
            "next_retry_at": row[4],
            "last_error": row[5],
        }
        for row in rows
    }


def save_metadata_fetch_status(
    appid,
    state,
    failure_count=0,
    next_retry_at=None,
    last_error=None,
):
    """Persist a metadata fetch/retry state."""

    now = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO metadata_fetch_status (
                appid,
                state,
                failure_count,
                last_failure_at,
                next_retry_at,
                last_error
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(appid)
            DO UPDATE SET
                state = excluded.state,
                failure_count = excluded.failure_count,
                last_failure_at = excluded.last_failure_at,
                next_retry_at = excluded.next_retry_at,
                last_error = excluded.last_error
            """,
            (
                int(appid),
                state,
                int(failure_count),
                now,
                next_retry_at,
                last_error,
            ),
        )


def clear_metadata_fetch_status(appid):
    """Clear failure state after a successful metadata fetch."""

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM metadata_fetch_status WHERE appid = ?",
            (int(appid),),
        )


def get_metadata_unavailable_appids():
    """Return AppIDs whose Steam Store metadata is currently unavailable."""

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT appid
            FROM metadata_fetch_status
            WHERE state = 'metadata_unavailable'
            """
        ).fetchall()

    return {int(row[0]) for row in rows}

