import streamlit as st

from constants import SMART_PICK_STATUSES
from smart_pick import smart_pick
from ui.common import open_game_dialog


@st.dialog(
    "🎲 What should I play next?",
    width="medium"
)
def show_smart_pick(df):

    st.caption(
        "Choose your criteria and the app will suggest a game "
        "from your library."
    )

    filter_col1, filter_col2 = st.columns(2)

    with filter_col1:

        smart_statuses = st.multiselect(
            "Statuses",
            SMART_PICK_STATUSES,
            default=[],
            placeholder="All statuses",
            key="smart_pick_statuses"
        )

        smart_genre = st.selectbox(
            "Genre",
            [
                "Any",
                "Action",
                "Adventure",
                "Casual",
                "Indie",
                "Massively Multiplayer",
                "Racing",
                "RPG",
                "Simulation",
                "Sports",
                "Strategy",
            ],
            key="smart_pick_genre"
        )

    with filter_col2:

        smart_category = st.selectbox(
            "Game mode",
            [
                "Any",
                "Single-player",
                "Multi-player",
                "Co-op",
                "Online Co-op",
            ],
            key="smart_pick_category"
        )

        smart_review_filter = st.selectbox(
            "Minimum positive reviews",
            [
                "Any",
                "70%+",
                "80%+",
                "90%+",
            ],
            key="smart_pick_reviews"
        )

    st.write("")

    smart_hltb_duration = st.selectbox(
        "HLTB Duration",
        [
            "Main Story",
            "Main + Extras",
            "Completionist",
        ],
        index=None,
        placeholder="No duration filter",
        key="smart_pick_hltb_duration",
    )

    min_hltb_hours = None
    max_hltb_hours = None

    if smart_hltb_duration is not None:
        duration_col1, duration_col2 = st.columns(2)

        with duration_col1:
            min_hltb_hours = st.number_input(
                "Min hours",
                min_value=0.0,
                value=None,
                step=1.0,
                placeholder="No minimum",
                key="smart_pick_hltb_min_hours",
            )

        with duration_col2:
            max_hltb_hours = st.number_input(
                "Max hours",
                min_value=0.0,
                value=None,
                step=1.0,
                placeholder="No maximum",
                key="smart_pick_hltb_max_hours",
            )

    hltb_duration_mapping = {
        "Main Story": "main_story",
        "Main + Extras": "main_extra",
        "Completionist": "completionist",
    }

    hltb_duration_type = (
        hltb_duration_mapping.get(
            smart_hltb_duration
        )
    )

    review_mapping = {
        "Any": None,
        "70%+": 70,
        "80%+": 80,
        "90%+": 90,
    }

    genre_filter = (
        None
        if smart_genre == "Any"
        else smart_genre
    )

    category_filter = (
        None
        if smart_category == "Any"
        else smart_category
    )

    minimum_reviews = review_mapping[
        smart_review_filter
    ]

    st.write("")

    if st.button(
        "🎲 Suggest a game",
        type="primary",
        width="stretch",
        key="run_smart_pick"
    ):

        if (
            min_hltb_hours is not None
            and max_hltb_hours is not None
            and min_hltb_hours > max_hltb_hours
        ):
            st.error(
                "Min hours cannot be greater than Max hours."
            )
            return

        effective_statuses = (
            smart_statuses
            if smart_statuses
            else SMART_PICK_STATUSES
        )

        with st.spinner(
            "Searching your library..."
        ):

            result = smart_pick(
                games=df.to_dict(
                    "records"
                ),
                statuses=effective_statuses,
                genre=genre_filter,
                category=category_filter,
                min_positive_percentage=minimum_reviews,
                hltb_duration_type=hltb_duration_type,
                min_hltb_hours=min_hltb_hours,
                max_hltb_hours=max_hltb_hours,
            )

        selected_game = result.get(
            "game"
        )

        if selected_game is None:

            if result["eligible_count"] == 0:

                st.info(
                    "🎮 There are no games available with the selected statuses."
                )

            else:

                st.info(
                    "🔎 No games matched these "
                    "criteria. Try relaxing the filters."
                )

                if result.get("metadata_required"):
                    st.caption(
                        f"{result['inspected_count']} of "
                        f"{result['eligible_count']} "
                        "eligible games currently have cached Steam metadata "
                        "for metadata-based filtering."
                    )

                if result.get("hltb_required"):
                    st.caption(
                        f"{result['hltb_inspected_count']} of "
                        f"{result['eligible_count']} "
                        "eligible games currently have matched HLTB metadata."
                    )

        else:

            appid = int(
                selected_game["AppID"]
            )

            st.session_state.smart_pick_context = {
                "statuses": list(
                    effective_statuses
                ),
                "genre": genre_filter,
                "category": category_filter,
                "min_positive_percentage": minimum_reviews,
                "hltb_duration_type": hltb_duration_type,
                "min_hltb_hours": min_hltb_hours,
                "max_hltb_hours": max_hltb_hours,
            }

            st.session_state.smart_pick_history = [
                appid
            ]

            open_game_dialog(
                appid,
                source="smart_pick"
            )

            st.rerun()
