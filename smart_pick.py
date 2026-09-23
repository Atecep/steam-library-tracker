import math
import random

from constants import (
    SMART_PICK_SAMPLE_SIZE,
    STATUS_BACKLOG,
    STATUS_PLAYING,
    STATUS_UNPLAYED,
)
from metadata_service import get_game_metadata


# =========================================================
# FILTERS
# =========================================================

def matches_genre(metadata, genre):
    """
    Check whether the game belongs to the selected genre.
    """

    if not genre:
        return True

    genres = metadata.get(
        "genres",
        []
    )

    genre = genre.lower()

    return any(
        item.lower() == genre
        for item in genres
    )


def matches_category(metadata, category):
    """
    Check categories such as:
    Single-player, Co-op, Online Co-op, etc.
    """

    if not category:
        return True

    categories = metadata.get(
        "categories",
        []
    )

    category = category.lower()

    return any(
        category in item.lower()
        for item in categories
    )


def matches_review_score(
    metadata,
    min_positive_percentage
):
    """
    Filter by the minimum percentage
    of positive reviews.
    """

    if min_positive_percentage is None:
        return True

    percentage = metadata.get(
        "positive_percentage"
    )

    if percentage is None:
        return False

    return (
        percentage
        >= min_positive_percentage
    )


# =========================================================
# SMART SCORE
# =========================================================

def calculate_smart_score(game, metadata):
    """
    Calculate a game's weight in Smart Pick.

    The score does not directly select the winner.
    It is used only as a weight in a random selection.

    The higher the score, the greater the chance
    of the game being selected.
    """

    score = 10.0

    status = game.get(
        "Status"
    )

    hours = float(
        game.get(
            "Hours",
            0
        )
        or 0
    )

    positive_percentage = metadata.get(
        "positive_percentage"
    )

    total_reviews = metadata.get(
        "total_reviews"
    ) or 0

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    # Games already started receive some priority,
    # because it makes sense to encourage continuing something
    # that already has time invested in it.

    status_bonus = {
        STATUS_PLAYING: 12,
        STATUS_BACKLOG: 7,
        STATUS_UNPLAYED: 3,
    }

    score += status_bonus.get(
        status,
        0
    )

    # -----------------------------------------------------
    # PLAYTIME
    # -----------------------------------------------------

    # This bonus only applies to games already started.
    #
    # A logarithm prevents a game with 300 hours
    # from completely outweighing a game with 10 hours.
    

    if (
        status
        in [
            STATUS_PLAYING,
            STATUS_BACKLOG,
        ]
        and hours > 0
    ):

        hours_bonus = (
            math.log1p(hours)
            * 3
        )

        # Maximum limit
        hours_bonus = min(
            hours_bonus,
            15
        )

        score += hours_bonus

    # -----------------------------------------------------
    # STEAM REVIEWS
    # -----------------------------------------------------

    if positive_percentage is not None:

        # A meaningful bonus only starts
        # above 60%.
        #
        # Approximate examples:
        #
        # 60% → +0
        # 70% → +4
        # 80% → +8
        # 90% → +12
        # 100% → +16

        review_bonus = max(
            0,
            (
                positive_percentage
                - 60
            )
            * 0.4
        )

        score += review_bonus

    # -----------------------------------------------------
    # REVIEW COUNT
    # -----------------------------------------------------

    # A 95% rating based on 100,000 reviews
    # is a stronger signal than 95% based on 5 reviews.
    #
    # The effect is deliberately small.

    if total_reviews > 0:

        confidence_bonus = min(
            math.log10(
                total_reviews + 1
            ),
            5
        )

        score += confidence_bonus

    # Never allow a zero or negative weight.
    return max(
        score,
        1.0
    )


# =========================================================
# SMART PICK
# =========================================================

def smart_pick(
    games,
    statuses,
    genre=None,
    category=None,
    min_positive_percentage=None,
    sample_size=SMART_PICK_SAMPLE_SIZE,
):
    """
    Select a game using weighted random selection.

    First:
        - filter by status
        - create a sample
        - fetch metadata
        - apply genre/category/review filters

    Then:
        - calculate the Smart Score
        - make a weighted random selection
    """

    # -----------------------------------------------------
    # Games eligible by status
    # -----------------------------------------------------

    eligible_games = [
        game
        for game in games
        if game.get("Status")
        in statuses
    ]

    if not eligible_games:

        return {
            "game": None,
            "eligible_count": 0,
            "inspected_count": 0,
            "matched_count": 0,
        }

    # -----------------------------------------------------
    # Random sample
    # -----------------------------------------------------

    sample_size = min(
        sample_size,
        len(eligible_games)
    )

    sample = random.sample(
        eligible_games,
        sample_size
    )

    candidates = []

    # -----------------------------------------------------
    # Metadata + filters
    # -----------------------------------------------------

    for game in sample:

        appid = int(
            game["AppID"]
        )

        try:

            metadata = get_game_metadata(
                appid
            )

        except Exception:

            # A problematic game should not
            # break the entire Smart Pick.
            continue

        if metadata is None:
            continue

        if not matches_genre(
            metadata,
            genre
        ):
            continue

        if not matches_category(
            metadata,
            category
        ):
            continue

        if not matches_review_score(
            metadata,
            min_positive_percentage
        ):
            continue

        # -------------------------------------------------
        # Smart Score
        # -------------------------------------------------

        smart_score = calculate_smart_score(
            game,
            metadata
        )

        candidate = {
            **game,

            "genres": metadata.get(
                "genres",
                []
            ),

            "categories": metadata.get(
                "categories",
                []
            ),

            "review_score": metadata.get(
                "review_score"
            ),

            "review_description": metadata.get(
                "review_description"
            ),

            "positive_percentage": metadata.get(
                "positive_percentage"
            ),

            "total_reviews": metadata.get(
                "total_reviews"
            ),

            "smart_score": smart_score,
        }

        candidates.append(
            candidate
        )

    # -----------------------------------------------------
    # No candidates
    # -----------------------------------------------------

    if not candidates:

        return {
            "game": None,

            "eligible_count": len(
                eligible_games
            ),

            "inspected_count": len(
                sample
            ),

            "matched_count": 0,
        }

    # -----------------------------------------------------
    # WEIGHTED SELECTION
    # -----------------------------------------------------

    weights = [
        candidate["smart_score"]
        for candidate in candidates
    ]

    selected_game = random.choices(
        candidates,
        weights=weights,
        k=1
    )[0]

    return {
        "game": selected_game,

        "eligible_count": len(
            eligible_games
        ),

        "inspected_count": len(
            sample
        ),

        "matched_count": len(
            candidates
        ),
    }