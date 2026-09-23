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