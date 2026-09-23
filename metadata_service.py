from datetime import datetime, timedelta

from database import (
    get_game_metadata as get_cached_metadata,
    save_game_metadata,
)

from steam_store import (
    get_game_metadata as fetch_steam_metadata,
)


CACHE_MAX_AGE_DAYS = 7


def is_cache_fresh(metadata):
    fetched_at = metadata.get("fetched_at")

    if not fetched_at:
        return False

    try:
        fetched_time = datetime.fromisoformat(fetched_at)
    except ValueError:
        return False

    max_age = timedelta(
        days=CACHE_MAX_AGE_DAYS
    )

    return (
        datetime.now() - fetched_time
        < max_age
    )


def get_game_metadata(
    appid,
    force_refresh=False
):
    appid = int(appid)

    cached = get_cached_metadata(appid)

    # Cache is still valid
    if (
        cached is not None
        and not force_refresh
        and is_cache_fresh(cached)
    ):
        return cached

    # Missing or stale cache:
    # try to fetch fresh data.
    try:
        metadata = fetch_steam_metadata(
            appid
        )

        if metadata is not None:
            save_game_metadata(metadata)

            return get_cached_metadata(
                appid
            )

    except Exception:
        # If Steam is unavailable,
        # use the old cache.
        if cached is not None:
            return cached

        raise

    # If the refresh fails but
    # cached data is available,
    # keep using it.
    if cached is not None:
        return cached

    return None