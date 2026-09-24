"""Gentle background population/refresh of Steam Store metadata.

The worker intentionally does not use Streamlit APIs. It runs as a daemon
thread in the Streamlit server process, updates SQLite one game at a time and
stops automatically when there is no due work left.
"""

import threading

import requests

from constants import (
    METADATA_BACKGROUND_BATCH_SIZE,
    METADATA_BACKGROUND_PAUSE_SECONDS,
    METADATA_NETWORK_BACKOFF_SECONDS,
    METADATA_RATE_LIMIT_BACKOFF_SECONDS,
    STATUS_BACKLOG,
    STATUS_FINISHED,
    STATUS_PLAYING,
    STATUS_UNPLAYED,
)
from database import (
    get_all_game_metadata,
    get_all_metadata_fetch_statuses,
)
from metadata_service import (
    get_game_metadata,
    is_cache_fresh,
    is_metadata_retry_due,
)
from steam_store import SteamStoreMetadataUnavailable


_STATUS_PRIORITY = {
    STATUS_BACKLOG: 0,
    STATUS_UNPLAYED: 1,
    STATUS_PLAYING: 2,
    STATUS_FINISHED: 3,
}

_state_lock = threading.Lock()
_worker_thread = None
_stop_event = threading.Event()
_library_games = []


def _normalise_library_games(games):
    """Keep only the AppID/status fields needed by the worker."""
    normalised = []
    seen = set()

    for game in games:
        appid = game.get("AppID", game.get("appid"))

        if appid is None:
            continue

        try:
            appid = int(appid)
        except (TypeError, ValueError):
            continue

        if appid in seen:
            continue

        seen.add(appid)
        normalised.append({
            "appid": appid,
            "status": game.get("Status", game.get("status")),
        })

    normalised.sort(
        key=lambda item: (
            _STATUS_PRIORITY.get(item["status"], 99),
            item["appid"],
        )
    )

    return normalised


def _current_library_games():
    with _state_lock:
        return list(_library_games)


def _candidate_appids(games):
    """Return due missing metadata first, then due stale metadata."""
    cached = get_all_game_metadata()
    fetch_statuses = get_all_metadata_fetch_statuses()
    missing = []
    stale = []

    for game in games:
        appid = game["appid"]
        fetch_status = fetch_statuses.get(appid)

        if (
            fetch_status is not None
            and not is_metadata_retry_due(fetch_status)
        ):
            continue

        metadata = cached.get(appid)

        if metadata is None:
            missing.append(appid)
        elif not is_cache_fresh(metadata):
            stale.append(appid)

    return missing + stale, len(missing), len(stale)


def _wait(seconds):
    """Interruptible sleep so shutdown/update is responsive."""
    return _stop_event.wait(seconds)


def _worker_loop():
    global _worker_thread

    print(
        "[metadata] Background refresh started "
        f"(1 game every {METADATA_BACKGROUND_PAUSE_SECONDS}s)."
    )

    total_updated = 0
    total_deferred = 0

    try:
        while not _stop_event.is_set():
            games = _current_library_games()

            if not games:
                break

            candidates, _, _ = _candidate_appids(games)

            if not candidates:
                print("[metadata] Cache is up to date for this library.")
                break

            # Build a small queue to avoid rescanning the whole SQLite cache
            # after every single game. Requests are still strictly sequential
            # with a pause after each one; there is no burst of 10 requests.
            batch = candidates[:METADATA_BACKGROUND_BATCH_SIZE]
            network_backoff = None

            for index, appid in enumerate(batch):
                if _stop_event.is_set():
                    break

                try:
                    metadata = get_game_metadata(
                        appid,
                        allow_stale_on_error=False,
                    )

                    if metadata is None or not is_cache_fresh(metadata):
                        total_deferred += 1
                    else:
                        total_updated += 1

                except SteamStoreMetadataUnavailable:
                    # metadata_service has already persisted the retry state
                    # and incremented delisted evidence for this AppID.
                    total_deferred += 1

                except requests.HTTPError as error:
                    total_deferred += 1
                    status_code = getattr(
                        getattr(error, "response", None),
                        "status_code",
                        None,
                    )

                    if status_code == 429:
                        network_backoff = METADATA_RATE_LIMIT_BACKOFF_SECONDS
                        print(
                            "[metadata] Steam rate limit detected; "
                            "background refresh is backing off."
                        )
                        break

                    if status_code is not None and status_code >= 500:
                        network_backoff = METADATA_NETWORK_BACKOFF_SECONDS
                        break

                except requests.RequestException:
                    total_deferred += 1
                    network_backoff = METADATA_NETWORK_BACKOFF_SECONDS
                    print(
                        "[metadata] Network problem; background refresh "
                        "is backing off."
                    )
                    break

                except Exception:
                    total_deferred += 1

                processed = total_updated + total_deferred

                if processed % 10 == 0:
                    _, remaining_missing, remaining_stale = _candidate_appids(
                        _current_library_games()
                    )
                    print(
                        "[metadata] Progress: "
                        f"{total_updated} updated, {total_deferred} deferred this session; "
                        f"{remaining_missing} missing + {remaining_stale} stale pending."
                    )

                # Smooth request rate: one game, then pause, including between
                # items in the internal queue.
                if index < len(batch) - 1:
                    if _wait(METADATA_BACKGROUND_PAUSE_SECONDS):
                        break

            if _stop_event.is_set():
                break

            if network_backoff is not None:
                if _wait(network_backoff):
                    break
            else:
                # Also pause between the last game in this queue and the first
                # game in the next queue so the request cadence stays uniform.
                if _wait(METADATA_BACKGROUND_PAUSE_SECONDS):
                    break

    finally:
        with _state_lock:
            _worker_thread = None

        print("[metadata] Background refresh stopped.")


def start_metadata_background_refresh(games):
    """Start or update the single background metadata worker."""
    global _worker_thread, _library_games

    normalised = _normalise_library_games(games)

    with _state_lock:
        _library_games = normalised

        if _worker_thread is not None and _worker_thread.is_alive():
            return False

        _stop_event.clear()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="steam-metadata-refresh",
            daemon=True,
        )
        _worker_thread.start()

    return True


def stop_metadata_background_refresh():
    """Ask the worker to stop. The daemon also dies with the app process."""
    _stop_event.set()
