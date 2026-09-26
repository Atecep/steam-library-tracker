"""Gentle background population/refresh of HowLongToBeat metadata.

The worker never calls Streamlit APIs. It processes one game at a time in a
daemon thread, sleeps between requests, and reports progress in groups of ten.
"""

from __future__ import annotations

import threading
import time

from constants import (
    HLTB_BACKGROUND_PAUSE_SECONDS,
    HLTB_BACKGROUND_PROGRESS_INTERVAL,
    HLTB_ERROR_BACKOFF_SECONDS,
    HLTB_REPEATED_ERROR_BACKOFF_SECONDS,
    STATUS_BACKLOG,
    STATUS_FINISHED,
    STATUS_PLAYING,
    STATUS_UNPLAYED,
)
from database import get_all_hltb_metadata
from hltb_service import get_hltb_metadata, is_hltb_cache_fresh


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
_completed_library_signature = None


def _normalise_library_games(games):
    """Keep only fields required by the HLTB worker."""
    normalised = []
    seen = set()

    for game in games:
        appid = game.get("AppID", game.get("appid"))
        name = game.get("Game", game.get("name"))

        try:
            appid = int(appid)
        except (TypeError, ValueError):
            continue

        name = str(name or "").strip()

        if not name or appid in seen:
            continue

        seen.add(appid)
        normalised.append(
            {
                "appid": appid,
                "name": name,
                "status": game.get("Status", game.get("status")),
            }
        )

    # Populate the games the user is most likely to care about first.
    normalised.sort(
        key=lambda item: (
            _STATUS_PRIORITY.get(item["status"], 99),
            item["appid"],
        )
    )

    return normalised


def _library_signature(games):
    return tuple(sorted(item["appid"] for item in games))


def _current_library_games():
    with _state_lock:
        return list(_library_games)


def _candidate_games(games, deferred_appids=None):
    """Return games whose HLTB cache is missing, expired, or invalidated."""
    cached = get_all_hltb_metadata()
    deferred_appids = deferred_appids or set()
    candidates = []

    for game in games:
        if game["appid"] in deferred_appids:
            continue

        metadata = cached.get(game["appid"])

        if metadata is None or not is_hltb_cache_fresh(metadata):
            candidates.append(game)

    return candidates


def _wait(seconds):
    """Interruptible sleep for responsive shutdown."""
    return _stop_event.wait(seconds)


def _print_progress(batch_results, session_processed, pending):
    matched = sum(1 for item in batch_results if item["result"] == "matched")
    no_match = sum(1 for item in batch_results if item["result"] == "no_match")
    errors = sum(1 for item in batch_results if item["result"] == "error")

    elapsed_values = [
        item["elapsed"]
        for item in batch_results
        if item["elapsed"] is not None
    ]
    avg = (
        sum(elapsed_values) / len(elapsed_values)
        if elapsed_values
        else 0.0
    )

    print(
        "[hltb] "
        f"{session_processed} processed: "
        f"{matched} matched, {no_match} no match, {errors} error"
        f"{'s' if errors != 1 else ''} in last {len(batch_results)} "
        f"| {pending} pending | avg {avg:.2f}s"
    )

    no_match_names = [
        item["name"]
        for item in batch_results
        if item["result"] == "no_match"
    ]
    error_names = [
        item["name"]
        for item in batch_results
        if item["result"] == "error"
    ]

    if no_match_names:
        print("[hltb]   no match: " + " | ".join(no_match_names))

    if error_names:
        print("[hltb]   errors: " + " | ".join(error_names))


def _worker_loop():
    global _worker_thread, _completed_library_signature

    print(
        "[hltb] Background population started "
        f"(1 game + {HLTB_BACKGROUND_PAUSE_SECONDS}s pause)."
    )

    session_processed = 0
    consecutive_errors = 0
    progress_batch = []
    error_attempts = {}
    deferred_appids = set()

    try:
        while not _stop_event.is_set():
            games = _current_library_games()

            if not games:
                break

            candidates = _candidate_games(
                games,
                deferred_appids=deferred_appids,
            )

            if not candidates:
                with _state_lock:
                    _completed_library_signature = _library_signature(games)

                if progress_batch:
                    _print_progress(
                        progress_batch,
                        session_processed,
                        0,
                    )
                    progress_batch = []

                if deferred_appids:
                    print(
                        "[hltb] "
                        f"{len(deferred_appids)} game(s) deferred after repeated "
                        "request errors; they will be tried again on a future app run."
                    )
                else:
                    print("[hltb] Cache is up to date for this library.")
                break

            # Work from the current snapshot. We rescan after each progress
            # group so cache changes caused by modal opens are picked up too.
            group = candidates[:HLTB_BACKGROUND_PROGRESS_INTERVAL]

            for game in group:
                if _stop_event.is_set():
                    break

                appid = game["appid"]
                name = game["name"]
                started = time.perf_counter()

                try:
                    metadata = get_hltb_metadata(
                        appid=appid,
                        game_name=name,
                    )
                    elapsed = time.perf_counter() - started

                    if metadata and metadata.get("state") == "matched":
                        result = "matched"
                    else:
                        result = "no_match"

                    consecutive_errors = 0
                    wait_seconds = HLTB_BACKGROUND_PAUSE_SECONDS

                except RuntimeError:
                    # HLTB/network failures are deliberately not converted into
                    # no-match cache entries by hltb_service.
                    elapsed = time.perf_counter() - started
                    result = "error"
                    consecutive_errors += 1
                    error_attempts[appid] = error_attempts.get(appid, 0) + 1

                    # Give one later retry during this worker run. If the same
                    # game fails twice, defer it for a future app run so one bad
                    # title/service hiccup cannot keep the worker looping forever.
                    if error_attempts[appid] >= 2:
                        deferred_appids.add(appid)

                    wait_seconds = (
                        HLTB_REPEATED_ERROR_BACKOFF_SECONDS
                        if consecutive_errors >= 2
                        else HLTB_ERROR_BACKOFF_SECONDS
                    )

                except Exception as error:
                    elapsed = time.perf_counter() - started
                    result = "error"
                    consecutive_errors += 1
                    error_attempts[appid] = error_attempts.get(appid, 0) + 1

                    if error_attempts[appid] >= 2:
                        deferred_appids.add(appid)

                    wait_seconds = (
                        HLTB_REPEATED_ERROR_BACKOFF_SECONDS
                        if consecutive_errors >= 2
                        else HLTB_ERROR_BACKOFF_SECONDS
                    )
                    print(
                        "[hltb] Unexpected background error for "
                        f"{name}: {type(error).__name__}"
                    )

                session_processed += 1
                progress_batch.append(
                    {
                        "name": name,
                        "result": result,
                        "elapsed": elapsed,
                    }
                )

                # Smooth cadence: every attempted game is followed by a pause.
                # Temporary errors back off more aggressively.
                if _wait(wait_seconds):
                    break

            if _stop_event.is_set():
                break

            remaining = len(
                _candidate_games(
                    _current_library_games(),
                    deferred_appids=deferred_appids,
                )
            )

            if progress_batch:
                _print_progress(
                    progress_batch,
                    session_processed,
                    remaining,
                )
                progress_batch = []

    finally:
        with _state_lock:
            _worker_thread = None

        print("[hltb] Background population stopped.")


def start_hltb_background_refresh(games):
    """Start or update the single HLTB background worker."""
    global _worker_thread, _library_games, _completed_library_signature

    normalised = _normalise_library_games(games)
    signature = _library_signature(normalised)

    with _state_lock:
        _library_games = normalised

        if _worker_thread is not None and _worker_thread.is_alive():
            return False

        if signature and signature == _completed_library_signature:
            return False

        _stop_event.clear()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="hltb-metadata-refresh",
            daemon=True,
        )
        _worker_thread.start()

    return True


def stop_hltb_background_refresh():
    """Ask the daemon worker to stop."""
    _stop_event.set()
