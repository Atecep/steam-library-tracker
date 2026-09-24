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
                        "eligible games currently have cached metadata "
                        "for metadata-based filtering."
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
            }

            st.session_state.smart_pick_history = [
                appid
            ]

            open_game_dialog(
                appid,
                source="smart_pick"
            )

            st.rerun()
