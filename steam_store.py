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


def get_store_details(appid):
    """
    Fetches information from the Steam Store page.

    Returns genres, categories, developers,
    publishers and other basic information.
    """

    params = {
        "appids": appid,
        "l": "english"
    }

    response = requests.get(
        APP_DETAILS_URL,
        params=params,
        headers=HEADERS,
        timeout=15
    )

    response.raise_for_status()

    payload = response.json()

    app_data = payload.get(
        str(appid),
        {}
    )

    if not app_data.get("success"):
        return None

    data = app_data.get(
        "data",
        {}
    )

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

        "name": data.get(
            "name"
        ),

        "type": data.get(
            "type"
        ),

        "genres": genres,

        "categories": categories,

        "developers": data.get(
            "developers",
            []
        ),

        "publishers": data.get(
            "publishers",
            []
        ),

        "release_date": data.get(
            "release_date",
            {}
        ).get(
            "date"
        ),

        "is_free": data.get(
            "is_free",
            False
        ),
    }


def get_review_summary(appid):
    """
    Fetches the Steam review summary.

    Does not download hundreds of reviews.
    Only query_summary is required.
    """

    url = REVIEWS_URL.format(
        appid=appid
    )

    params = {
        "json": 1,
        "language": "all",
        "purchase_type": "all",
        "filter": "all",
        "num_per_page": 1
    }

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    if data.get("success") != 1:
        return None

    summary = data.get(
        "query_summary",
        {}
    )

    total_positive = summary.get(
        "total_positive",
        0
    )

    total_negative = summary.get(
        "total_negative",
        0
    )

    total_reviews = summary.get(
        "total_reviews",
        0
    )

    if total_reviews > 0:

        positive_percentage = (
            total_positive
            / total_reviews
            * 100
        )

    else:

        positive_percentage = None

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

        "positive_percentage": (
            round(
                positive_percentage,
                1
            )
            if positive_percentage is not None
            else None
        ),
    }


def get_game_metadata(appid):
    """
    Combines Store Details + Reviews
    into a single result.
    """

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
        "reviews": reviews
    }