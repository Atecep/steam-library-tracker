import math
import random

from constants import (
    STATUS_BACKLOG,
    STATUS_PLAYING,
    STATUS_UNPLAYED,
)
from database import get_all_game_metadata


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
):
    """Select a game using weighted random selection.

    Smart Pick never fetches metadata from Steam. When the selected criteria
    do not require metadata, every eligible game can participate, including
    games whose metadata is still missing or marked Possibly delisted.

    Metadata becomes mandatory only when the user selects a genre, game mode
    or minimum review score.
    """

    eligible_games = [
        game
        for game in games
        if game.get("Status") in statuses
    ]

    if not eligible_games:
        return {
            "game": None,
            "eligible_count": 0,
            "inspected_count": 0,
            "matched_count": 0,
            "metadata_required": False,
        }

    cached_metadata = get_all_game_metadata()

    metadata_required = any([
        genre is not None,
        category is not None,
        min_positive_percentage is not None,
    ])

    games_with_metadata_count = sum(
        1
        for game in eligible_games
        if int(game["AppID"]) in cached_metadata
    )

    candidates = []

    for game in eligible_games:
        appid = int(game["AppID"])
        metadata = cached_metadata.get(appid)

        if metadata_required and metadata is None:
            continue

        # With no metadata-dependent filters, missing metadata is valid.
        # The score simply falls back to status/playtime weighting.
        metadata_for_scoring = metadata or {}

        if not matches_genre(metadata_for_scoring, genre):
            continue

        if not matches_category(metadata_for_scoring, category):
            continue

        if not matches_review_score(
            metadata_for_scoring,
            min_positive_percentage,
        ):
            continue

        smart_score = calculate_smart_score(
            game,
            metadata_for_scoring,
        )

        candidate = {
            **game,
            "genres": metadata_for_scoring.get("genres", []),
            "categories": metadata_for_scoring.get("categories", []),
            "review_score": metadata_for_scoring.get("review_score"),
            "review_description": metadata_for_scoring.get(
                "review_description"
            ),
            "positive_percentage": metadata_for_scoring.get(
                "positive_percentage"
            ),
            "total_reviews": metadata_for_scoring.get("total_reviews"),
            "smart_score": smart_score,
        }

        candidates.append(candidate)

    if not candidates:
        return {
            "game": None,
            "eligible_count": len(eligible_games),
            "inspected_count": (
                games_with_metadata_count
                if metadata_required
                else len(eligible_games)
            ),
            "matched_count": 0,
            "metadata_required": metadata_required,
        }

    weights = [
        candidate["smart_score"]
        for candidate in candidates
    ]

    selected_game = random.choices(
        candidates,
        weights=weights,
        k=1,
    )[0]

    return {
        "game": selected_game,
        "eligible_count": len(eligible_games),
        "inspected_count": (
            games_with_metadata_count
            if metadata_required
            else len(eligible_games)
        ),
        "matched_count": len(candidates),
        "metadata_required": metadata_required,
    }

