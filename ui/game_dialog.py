import math

import streamlit as st

from constants import (
    METADATA_STATE_METADATA_UNAVAILABLE,
    STATUSES,
)
from database import (
    get_metadata_fetch_status,
    save_game_data,
)
from metadata_service import get_game_metadata
from hltb_service import get_hltb_metadata, set_manual_hltb_metadata
from smart_pick import smart_pick
from ui.common import (
    clear_selected_game,
    get_game_image,
)


def _compact_metric(label, value):
    st.markdown(
        f"""
        <div class="compact-metric">
            <div class="compact-metric-label">{label}</div>
            <div class="compact-metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _slt_review_score(positive_percentage, total_reviews):
    """Return the 95% Wilson lower bound used by SLT Review Score."""
    if (
        positive_percentage is None
        or total_reviews is None
        or total_reviews <= 0
    ):
        return None

    p_hat = max(0.0, min(1.0, float(positive_percentage) / 100.0))
    n = float(total_reviews)
    z = 1.96
    z_squared = z * z

    numerator = (
        p_hat
        + z_squared / (2.0 * n)
        - z * math.sqrt(
            (p_hat * (1.0 - p_hat) / n)
            + z_squared / (4.0 * n * n)
        )
    )
    denominator = 1.0 + z_squared / n

    return (numerator / denominator) * 100.0


@st.dialog(
    "Game details",
    width="medium",
    on_dismiss=clear_selected_game
)
def show_game_details(game, df):

    appid = int(game["AppID"])
    game_name = game["Game"]
    hours = float(game["Hours"])
    current_status = game["Status"]
    current_notes = game["Notes"]

    st.markdown(
        """
        <style>
        [data-testid="stDialog"] .compact-metric {
            padding: 0.05rem 0 0.15rem 0;
        }

        [data-testid="stDialog"] .compact-metric-label {
            font-size: 0.76rem;
            line-height: 1.15;
            opacity: 0.88;
            margin-bottom: 0.18rem;
        }

        [data-testid="stDialog"] .compact-metric-value {
            font-size: 1.55rem;
            line-height: 1.08;
            font-weight: 400;
            letter-spacing: -0.02em;
        }

        [data-testid="stDialog"] .compact-section-title {
            font-size: 0.91rem;
            font-weight: 600;
            margin: 0.2rem 0 0.35rem 0;
        }

        [data-testid="stDialog"] .compact-caption {
            font-size: 0.74rem;
            opacity: 0.68;
            margin: -0.05rem 0 0.15rem 0;
        }

        [data-testid="stDialog"] .review-secondary-row {
            font-size: 0.74rem;
            opacity: 0.68;
            margin: -0.05rem 0 0.15rem 0;
        }

        [data-testid="stDialog"] .section-gap {
            height: 0.45rem;
        }

        [data-testid="stDialog"] .secondary-info {
            font-size: 0.76rem;
            opacity: 0.76;
            margin: 0.1rem 0 0.1rem 0;
        }

        [data-testid="stDialog"] .technical-caption {
            font-size: 0.69rem;
            opacity: 0.48;
            margin-top: 0.1rem;
        }

        [data-testid="stDialog"] hr {
            margin-top: 0.6rem;
            margin-bottom: 0.6rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # =====================================================
    # STEAM METADATA
    # =====================================================

    metadata_load_failed = False

    try:
        metadata = get_game_metadata(appid)
    except Exception:
        metadata = None
        metadata_load_failed = True

    metadata_fetch_status = get_metadata_fetch_status(appid)
    metadata_unavailable = (
        metadata_fetch_status is not None
        and metadata_fetch_status.get("state")
        == METADATA_STATE_METADATA_UNAVAILABLE
    )

    genres = []
    categories = []
    developers = []
    publishers = []

    review_description = None
    positive_percentage = None
    total_reviews = None

    if metadata:

        genres = metadata.get(
            "genres",
            []
        )

        categories = metadata.get(
            "categories",
            []
        )

        developers = metadata.get(
            "developers",
            []
        )

        publishers = metadata.get(
            "publishers",
            []
        )

        review_description = metadata.get(
            "review_description"
        )

        positive_percentage = metadata.get(
            "positive_percentage"
        )

        total_reviews = metadata.get(
            "total_reviews"
        )

    relevant_categories = [
        category
        for category in categories
        if any(
            keyword in category.lower()
            for keyword in [
                "single-player",
                "multi-player",
                "co-op",
                "pvp",
            ]
        )
    ]

    # =====================================================
    # HOWLONGTOBEAT
    # =====================================================

    hltb = None
    hltb_load_failed = False

    try:
        hltb = get_hltb_metadata(appid, game_name)
    except Exception:
        # HLTB is an optional third-party source. A temporary failure must
        # never prevent the rest of the game modal from opening.
        hltb_load_failed = True

    hltb_matched = (
        hltb is not None
        and hltb.get("state") == "matched"
    )

    # =====================================================
    # BANNER
    # =====================================================

    image_url = get_game_image(appid)

    st.markdown(
        f"""
        <div style="
            width: 100%;
            height: 230px;
            overflow: hidden;
            border-radius: 8px;
            margin-bottom: 8px;
        ">
            <img
                src="{image_url}"
                style="
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                    display: block;
                "
            >
        </div>
        """,
        unsafe_allow_html=True
    )

    # =====================================================
    # TITLE + STATUS
    # =====================================================

    title_col, status_col = st.columns(
        [4, 1.3],
        vertical_alignment="center"
    )

    with title_col:

        st.subheader(
            game_name
        )

    with status_col:

        st.markdown(
            f"**{current_status}**"
        )

    # =====================================================
    # METRICS
    # =====================================================

    metric_col1, metric_col2, metric_col3 = st.columns(3)

    with metric_col1:
        _compact_metric(
            "⏱️ Playtime",
            f"{hours:.1f} h",
        )

    with metric_col2:
        _compact_metric(
            "👍 Positive (%)",
            (
                f"{positive_percentage:.1f}%"
                if positive_percentage is not None
                else "—"
            ),
        )

    with metric_col3:
        _compact_metric(
            "💬 Reviews",
            (
                f"{int(total_reviews):,}"
                if total_reviews is not None
                else "—"
            ),
        )

    slt_score = _slt_review_score(positive_percentage, total_reviews)

    if review_description or slt_score is not None:
        review_secondary_parts = []
        if review_description:
            review_secondary_parts.append(f"Steam: {review_description}")
        if slt_score is not None:
            review_secondary_parts.append(f"SLT Score: {slt_score:.1f}%")

        st.markdown(
            f'<div class="review-secondary-row">{" · ".join(review_secondary_parts)}</div>',
            unsafe_allow_html=True,
        )

    if hltb_matched:
        st.markdown(
            '<div class="section-gap"></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="compact-section-title">⏳ HowLongToBeat</div>',
            unsafe_allow_html=True,
        )

        hltb_col1, hltb_col2, hltb_col3 = st.columns(3)

        with hltb_col1:
            _compact_metric(
                "Main Story",
                (
                    f"{hltb['main_story']:.1f} h"
                    if hltb.get("main_story") is not None
                    else "—"
                ),
            )

        with hltb_col2:
            _compact_metric(
                "Main + Extras",
                (
                    f"{hltb['main_extra']:.1f} h"
                    if hltb.get("main_extra") is not None
                    else "—"
                ),
            )

        with hltb_col3:
            _compact_metric(
                "Completionist",
                (
                    f"{hltb['completionist']:.1f} h"
                    if hltb.get("completionist") is not None
                    else "—"
                ),
            )

    elif hltb is not None and hltb.get("state") == "no_match":
        st.caption(
            "⏳ HowLongToBeat: no reliable name match found."
        )

        with st.form(
            f"hltb_manual_match_{appid}",
            border=False,
        ):
            manual_id_col, manual_button_col = st.columns(
                [3, 1],
                vertical_alignment="bottom",
            )

            with manual_id_col:
                manual_hltb_id = st.text_input(
                    "HLTB ID",
                    placeholder="e.g. 3126",
                    key=f"hltb_manual_id_{appid}",
                )

            with manual_button_col:
                use_manual_hltb_id = st.form_submit_button(
                    "Use HLTB ID",
                    use_container_width=True,
                )

            if use_manual_hltb_id:
                try:
                    manual_hltb_id = manual_hltb_id.strip()

                    if not manual_hltb_id:
                        raise ValueError("Enter an HLTB ID.")

                    set_manual_hltb_metadata(
                        appid=appid,
                        game_name=game_name,
                        hltb_id=manual_hltb_id,
                    )

                except ValueError as error:
                    st.error(str(error))

                except RuntimeError:
                    st.error(
                        "Could not load that HLTB ID. "
                        "Check the ID and try again."
                    )

                except Exception:
                    st.error(
                        "HowLongToBeat could not be reached at the moment."
                    )

                else:
                    st.rerun()

    elif hltb_load_failed:
        st.caption(
            "⚠️ HowLongToBeat data could not be loaded at the moment."
        )

    if hltb_matched:
        st.markdown(
            '<div class="section-gap"></div>',
            unsafe_allow_html=True,
        )

    if metadata_unavailable:

        st.caption(
            "⚠️ Metadata unavailable. Steam is not currently returning "
            "Store metadata for this game. This can happen with removed "
            "titles, special editions, unavailable Store pages, or other "
            "Steam catalogue cases. The app will retry automatically."
        )

    elif metadata_load_failed:

        st.caption(
            "⚠️ Could not load all Steam metadata "
            "at the moment."
        )

    # =====================================================
    # GENRES + MODES
    # =====================================================

    metadata_col1, metadata_col2 = st.columns(2)

    with metadata_col1:

        st.markdown(
            '<div class="compact-section-title">🎭 Genres</div>',
            unsafe_allow_html=True,
        )

        if genres:

            st.write(
                " · ".join(genres)
            )

        else:

            st.caption(
                "No information"
            )

    with metadata_col2:

        st.markdown(
            '<div class="compact-section-title">🎮 Modes</div>',
            unsafe_allow_html=True,
        )

        if relevant_categories:

            st.write(
                " · ".join(
                    relevant_categories
                )
            )

        else:

            st.caption(
                "No information"
            )

    # =====================================================
    # DEVELOPER / PUBLISHER
    # =====================================================

    secondary_info = []

    if developers:

        secondary_info.append(
            "Developed by "
            + ", ".join(developers)
        )

    if publishers:

        secondary_info.append(
            "Published by "
            + ", ".join(publishers)
        )

    if secondary_info:

        st.markdown(
            f'<div class="secondary-info">{" · ".join(secondary_info)}</div>',
            unsafe_allow_html=True,
        )

    # =====================================================
    # PERSONAL DATA
    # =====================================================

    st.divider()

    status = st.selectbox(
        "Status",
        STATUSES,
        index=(
            STATUSES.index(current_status)
            if current_status in STATUSES
            else 0
        ),
        key=f"detail_status_{appid}"
    )

    notes = st.text_area(
        "Notes",
        value=current_notes,
        height=100,
        key=f"detail_notes_{appid}",
        placeholder=(
            "Thoughts, where I left off, "
            "what I want to do next..."
        )
    )

    # =====================================================
    # SMART PICK REROLL
    # =====================================================

    came_from_smart_pick = (
        st.session_state.get(
            "game_dialog_source"
        )
        == "smart_pick"
    )

    smart_pick_context = (
        st.session_state.get(
            "smart_pick_context"
        )
    )

    if (
        came_from_smart_pick
        and smart_pick_context
    ):

        if st.button(
            "🎲 Another suggestion",
            width="stretch",
            key=f"smart_pick_reroll_{appid}"
        ):

            previous_appids = set(
                st.session_state.get(
                    "smart_pick_history",
                    []
                )
            )

            candidate_games = [
                game_record
                for game_record in df.to_dict(
                    "records"
                )
                if int(
                    game_record["AppID"]
                )
                not in previous_appids
            ]

            with st.spinner(
                "Looking for another suggestion..."
            ):

                reroll_result = smart_pick(
                    games=candidate_games,
                    statuses=smart_pick_context[
                        "statuses"
                    ],
                    genre=smart_pick_context[
                        "genre"
                    ],
                    category=smart_pick_context[
                        "category"
                    ],
                    min_positive_percentage=(
                        smart_pick_context[
                            "min_positive_percentage"
                        ]
                    ),
                    hltb_duration_type=(
                        smart_pick_context.get(
                            "hltb_duration_type"
                        )
                    ),
                    min_hltb_hours=(
                        smart_pick_context.get(
                            "min_hltb_hours"
                        )
                    ),
                    max_hltb_hours=(
                        smart_pick_context.get(
                            "max_hltb_hours"
                        )
                    ),
                )

            reroll_game = reroll_result.get(
                "game"
            )

            if reroll_game is None:

                st.session_state[
                    "smart_pick_reroll_message"
                ] = (
                    "Could not find another suggestion "
                    "with the same criteria."
                )

            else:

                reroll_appid = int(
                    reroll_game["AppID"]
                )

                history = list(
                    st.session_state.get(
                        "smart_pick_history",
                        []
                    )
                )

                history.append(
                    reroll_appid
                )

                st.session_state[
                    "smart_pick_history"
                ] = history

                st.session_state[
                    "selected_game_appid"
                ] = reroll_appid

                st.session_state[
                    "game_dialog_source"
                ] = "smart_pick"

                st.session_state.pop(
                    "smart_pick_reroll_message",
                    None
                )

                st.rerun()

        reroll_message = st.session_state.pop(
            "smart_pick_reroll_message",
            None
        )

        if reroll_message:

            st.info(
                reroll_message
            )

    # =====================================================
    # ACTIONS
    # =====================================================

    action_col1, action_col2, action_col3 = st.columns(3)

    with action_col1:

        if st.button(
            "💾 Save",
            type="primary",
            width="stretch",
            key=f"detail_save_{appid}"
        ):

            save_game_data(
                appid=appid,
                status=status,
                notes=notes
            )

            gallery_status_key = (
                f"gallery_status_{appid}"
            )

            if gallery_status_key in st.session_state:

                st.session_state[
                    gallery_status_key
                ] = status

            # Keep the game dialog open after saving.
            # The full rerun reloads the row from SQLite, while
            # selected_game_appid/open_game_dialog remain in session state.
            st.rerun()

    with action_col2:

        st.link_button(
            "▶️ Play / Install",
            f"steam://launch/{appid}/dialog",
            width="stretch",
            help=(
                "Open this game in the Steam client. "
                "Steam will offer installation if needed."
            )
        )

    with action_col3:

        st.link_button(
            "🛒 Open in Steam",
            (
                "https://store.steampowered.com/"
                f"app/{appid}/"
            ),
            width="stretch"
        )

    st.markdown(
        f'<div class="technical-caption">Steam AppID: {appid}</div>',
        unsafe_allow_html=True,
    )


def show_selected_game_dialog(df):
    selected_appid = st.session_state.get(
        "selected_game_appid"
    )

    if (
        selected_appid is None
        or not st.session_state.get(
            "open_game_dialog",
            False
        )
    ):
        return

    selected_rows = df[
        df["AppID"] == int(selected_appid)
    ]

    if selected_rows.empty:
        clear_selected_game()
        return

    selected_game_data = (
        selected_rows
        .iloc[0]
        .to_dict()
    )

    show_game_details(
        selected_game_data,
        df
    )
