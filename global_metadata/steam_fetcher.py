from __future__ import annotations

import requests


APP_DETAILS_URL = (
    "https://store.steampowered.com/api/appdetails"
)

REVIEWS_URL = (
    "https://store.steampowered.com/appreviews/{appid}"
)

HEADERS = {
    "User-Agent": "SteamLibraryTracker/0.1"
}


def _find_app_entry(payload, appid):
    """Return the response entry for the requested Steam AppID."""
    appid = int(appid)

    direct = payload.get(str(appid))

    if isinstance(direct, dict):
        data = direct.get("data") or {}

        if (
            direct.get("success")
            and int(data.get("steam_appid", appid)) == appid
        ):
            return direct

    for entry in payload.values():
        if not isinstance(entry, dict):
            continue

        if not entry.get("success"):
            continue

        data = entry.get("data") or {}

        try:
            returned_appid = int(data.get("steam_appid"))
        except (TypeError, ValueError):
            continue

        if returned_appid == appid:
            return entry

    return None


def _request_store_entry(appid, cc=None):
    params = {
        "appids": int(appid),
        "l": "english",
    }

    if cc:
        params["cc"] = cc

    response = requests.get(
        APP_DETAILS_URL,
        params=params,
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, dict):
        return None

    return _find_app_entry(
        payload,
        appid,
    )


def get_store_details(appid):
    appid = int(appid)

    # First try the runner's normal/default Steam market.
    app_data = _request_store_entry(
        appid
    )

    # If the title is unavailable in the runner's market, retry using
    # the US store so the global database does not depend on runner region.
    if app_data is None:
        app_data = _request_store_entry(
            appid,
            cc="us",
        )

    if app_data is None:
        return None

    data = app_data.get("data") or {}

    genres = [
        genre.get("description")
        for genre in data.get("genres", [])
        if genre.get("description")
    ]

    categories = [
        category.get("description")
        for category in data.get("categories", [])
        if category.get("description")
    ]

    return {
        "appid": appid,
        "name": data.get("name"),
        "type": data.get("type"),
        "genres": genres,
        "categories": categories,
        "developers": data.get(
            "developers",
            [],
        ),
        "publishers": data.get(
            "publishers",
            [],
        ),
        "release_date": (
            data.get("release_date") or {}
        ).get("date"),
        "is_free": bool(
            data.get("is_free", False)
        ),
    }


def get_review_summary(appid):
    appid = int(appid)

    response = requests.get(
        REVIEWS_URL.format(appid=appid),
        params={
            "json": 1,
            "language": "all",
            "purchase_type": "all",
            "filter": "all",
            "num_per_page": 1,
        },
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()

    if data.get("success") != 1:
        return None

    summary = data.get(
        "query_summary",
        {},
    )

    total_positive = int(
        summary.get("total_positive", 0) or 0
    )
    total_negative = int(
        summary.get("total_negative", 0) or 0
    )
    total_reviews = int(
        summary.get("total_reviews", 0) or 0
    )

    positive_percentage = (
        round(
            total_positive
            / total_reviews
            * 100,
            1,
        )
        if total_reviews > 0
        else None
    )

    return {
        "review_score": summary.get(
            "review_score"
        ),
        "review_description": summary.get(
            "review_score_desc"
        ),
        "total_positive": total_positive,
        "total_negative": total_negative,
        "total_reviews": total_reviews,
        "positive_percentage": positive_percentage,
    }


def get_game_metadata(appid):
    store_details = get_store_details(
        appid
    )

    if store_details is None:
        return None

    reviews = get_review_summary(
        appid
    )

    return {
        **store_details,
        "reviews": reviews,
    }
