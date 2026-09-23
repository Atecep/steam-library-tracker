import streamlit as st

from constants import STATUSES
from database import save_game_data
from metadata_service import get_game_metadata
from smart_pick import smart_pick
from ui.common import (
    clear_selected_game,
    get_game_image,
)


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

    # =====================================================
    # STEAM METADATA
    # =====================================================

    metadata_load_failed = False

    try:
        metadata = get_game_metadata(appid)
    except Exception:
        metadata = None
        metadata_load_failed = True

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

        st.metric(
            "⏱️ Playtime",
            f"{hours:.1f} h"
        )

    with metric_col2:

        st.metric(
            "👍 Positive (%)",
            (
                f"{positive_percentage:.1f}%"
                if positive_percentage is not None
                else "—"
            )
        )

    with metric_col3:

        st.metric(
            "💬 Reviews",
            (
                f"{total_reviews:,}"
                if total_reviews
                else "—"
            )
        )

    if review_description:

        st.caption(
            f"Steam: {review_description}"
        )

    if metadata_load_failed:

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
            "**🎭 Genres**"
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
            "**🎮 Modes**"
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

        st.caption(
            " · ".join(
                secondary_info
            )
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

    action_col1, action_col2 = st.columns(2)

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

            clear_selected_game()

            st.rerun()

    with action_col2:

        st.link_button(
            "🛒 Open in Steam",
            (
                "https://store.steampowered.com/"
                f"app/{appid}/"
            ),
            width="stretch"
        )

    st.caption(
        f"Steam AppID: {appid}"
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
