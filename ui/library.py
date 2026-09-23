import altair as alt
import pandas as pd
import streamlit as st

from constants import (
    GAMES_PER_ROW,
    PAGE_SIZE,
    STATUSES,
    STATUS_BACKLOG,
    STATUS_FINISHED,
    STATUS_PLAYING,
    STATUS_UNPLAYED,
)
from ui.common import (
    get_game_image,
    open_game_dialog,
    save_gallery_status,
    shorten_game_title,
)
from ui.smart_pick_dialog import show_smart_pick


def _selected_statuses_from_chart_state(chart_state):
    """Extract selected statuses from an Altair/Streamlit event."""

    if not chart_state:
        return []

    try:
        selection = chart_state["selection"]
    except (KeyError, TypeError):
        try:
            selection = chart_state.selection
        except AttributeError:
            return []

    try:
        selected_points = selection[
            "library_status_selection"
        ]
    except (KeyError, TypeError):
        try:
            selected_points = (
                selection.library_status_selection
            )
        except AttributeError:
            return []

    selected_statuses = []

    for point in selected_points or []:

        if isinstance(point, dict):
            status = point.get("Filter")
        else:
            try:
                status = point["Filter"]
            except (KeyError, TypeError):
                status = None

        if (
            status in STATUSES
            and status not in selected_statuses
        ):
            selected_statuses.append(status)

    return selected_statuses

def _refresh_library_status_chart():
    """Force the chart to reflect the current status filter."""
    st.session_state.library_status_chart_version += 1


def render_library_overview(
    total_games,
    playing_games,
    backlog_games,
    unplayed_games,
    finished_games
):
    """Display and control the filter through the segmented bar."""

    status_data = [
        {
            "Status": "Playing",
            "Filter": STATUS_PLAYING,
            "Games": playing_games,
            "Icon": "🟣",
        },
        {
            "Status": "Backlog",
            "Filter": STATUS_BACKLOG,
            "Games": backlog_games,
            "Icon": "🔵",
        },
        {
            "Status": "Never played",
            "Filter": STATUS_UNPLAYED,
            "Games": unplayed_games,
            "Icon": "🟠",
        },
        {
            "Status": "Finished",
            "Filter": STATUS_FINISHED,
            "Games": finished_games,
            "Icon": "🟢",
        },
    ]

    for item in status_data:
        item["Percentage"] = (
            item["Games"] / total_games * 100
            if total_games > 0
            else 0
        )
        item["Group"] = "Library"

    selected_statuses = list(
        st.session_state.get(
            "status_filters",
            []
        )
    )

    # The Altair selection is used only to detect the clicked segment.
    # The actual filter state lives in st.session_state["status_filters"].
    #
    # This avoids a Streamlit/Altair issue when only one status is selected:
    # the chart selection may look active while the widget's internal
    # selection remains empty, so clicking the only segment to deselect it
    # may not trigger a change.
    if "library_status_chart_version" not in st.session_state:
        st.session_state.library_status_chart_version = 0

    chart_version = st.session_state.library_status_chart_version

    chart_key = (
        "library_status_chart_"
        + str(chart_version)
    )

    status_selection = alt.selection_point(
        name="library_status_selection",
        fields=["Filter"],
        toggle=False,
        clear=False
    )

    for item in status_data:
        item["Selected"] = (
            not selected_statuses
            or item["Filter"] in selected_statuses
        )

    chart_data = pd.DataFrame(status_data)

    st.markdown(
        f"**🎮 {total_games} games in your library**"
    )

    chart = (
        alt.Chart(chart_data)
        .mark_bar(
            cornerRadius=5
        )
        .encode(
            x=alt.X(
                "Games:Q",
                stack="zero",
                axis=None,
                title=None,
                scale=alt.Scale(
                    domain=[0, total_games],
                    nice=False
                )
            ),
            y=alt.Y(
                "Group:N",
                axis=None,
                title=None
            ),
            color=alt.Color(
                "Status:N",
                scale=alt.Scale(
                    domain=[
                        "Playing",
                        "Backlog",
                        "Never played",
                        "Finished",
                    ],
                    range=[
                        "#A855F7",
                        "#2D8CFF",
                        "#FF9800",
                        "#7CB342",
                    ]
                ),
                legend=None
            ),
            opacity=alt.condition(
                "datum.Selected",
                alt.value(1.0),
                alt.value(0.28)
            ),
            tooltip=[
                alt.Tooltip(
                    "Status:N",
                    title="Status"
                ),
                alt.Tooltip(
                    "Games:Q",
                    title="Games",
                    format=",.0f"
                ),
                alt.Tooltip(
                    "Percentage:Q",
                    title="Percentage",
                    format=".1f"
                ),
            ]
        )
        .add_params(
            status_selection
        )
        .properties(
            height=38
        )
    )

    def sync_status_filter_from_chart():
        chart_state = st.session_state.get(
            chart_key
        )

        clicked_statuses = (
            _selected_statuses_from_chart_state(
                chart_state
            )
        )

        if not clicked_statuses:
            return

        clicked_status = clicked_statuses[-1]

        current_statuses = list(
            st.session_state.get(
                "status_filters",
                []
            )
        )

        if clicked_status in current_statuses:
            current_statuses.remove(
                clicked_status
            )
        else:
            current_statuses.append(
                clicked_status
            )

        st.session_state.status_filters = (
            current_statuses
        )

        # New chart instance: the internal selection resets to empty.
        # This makes each click behave like a true toggle.
        st.session_state.library_status_chart_version += 1

    st.altair_chart(
        chart,
        width="stretch",
        key=chart_key,
        on_select=sync_status_filter_from_chart,
        selection_mode="library_status_selection"
    )

    legend_columns = st.columns(4)

    for column, item in zip(
        legend_columns,
        status_data
    ):
        with column:
            st.caption(
                f"{item['Icon']} {item['Status']}: "
                f"{item['Games']} · "
                f"{item['Percentage']:.1f}%"
            )

def render_library(df):
    total_games = len(df)

    status_counts = df["Status"].value_counts()

    finished_games = int(
        status_counts.get(
            STATUS_FINISHED,
            0
        )
    )

    playing_games = int(
        status_counts.get(
            STATUS_PLAYING,
            0
        )
    )

    backlog_games = int(
        status_counts.get(
            STATUS_BACKLOG,
            0
        )
    )

    unplayed_games = int(
        status_counts.get(
            STATUS_UNPLAYED,
            0
        )
    )

    # =====================================================
    # LIBRARY OVERVIEW
    # =====================================================

    render_library_overview(
        total_games=total_games,
        playing_games=playing_games,
        backlog_games=backlog_games,
        unplayed_games=unplayed_games,
        finished_games=finished_games
    )

    if st.session_state.pop(
        "open_smart_pick_dialog",
        False
    ):
        show_smart_pick(df)

    # =====================================================
    # LIBRARY TOOLBAR
    # =====================================================

    search_col, status_col, sort_col, order_col = st.columns(
        [2.4, 1.6, 1, 1]
    )

    # -----------------------------------------------------
    # Search
    # -----------------------------------------------------

    with search_col:

        search_term = st.text_input(
            "🔎 Search",
            placeholder=(
                "e.g. Borderlands, Resident Evil, Mass Effect..."
            ),
            key="library_search"
        )

    # -----------------------------------------------------
    # Status
    # -----------------------------------------------------

    with status_col:

        status_filters = st.multiselect(
            "Status",
            STATUSES,
            key="status_filters",
            placeholder="All statuses",
            on_change=_refresh_library_status_chart
        )

    # -----------------------------------------------------
    # Sort by
    # -----------------------------------------------------

    with sort_col:

        sort_by = st.selectbox(
            "Sort by",
            [
                "Hours",
                "Name",
            ],
            key="library_sort"
        )

    # -----------------------------------------------------
    # Order
    # -----------------------------------------------------

    with order_col:

        order = st.selectbox(
            "Order",
            [
                "Descending",
                "Ascending",
            ],
            key="library_order"
        )

    # =====================================================
    # SEARCH + FILTERS
    # =====================================================

    filtered_df = df.copy()

    # -----------------------------------------------------
    # Search
    # -----------------------------------------------------

    if search_term:

        filtered_df = filtered_df[
            filtered_df["Game"]
            .str.contains(
                search_term,
                case=False,
                na=False
            )
        ]

    # -----------------------------------------------------
    # Status
    # -----------------------------------------------------

    if status_filters:

        filtered_df = filtered_df[
            filtered_df["Status"].isin(
                status_filters
            )
        ]

    # =====================================================
    # SORTING
    # =====================================================

    ascending = (
        order == "Ascending"
    )

    # -----------------------------------------------------
    # Hours
    # -----------------------------------------------------

    if sort_by == "Hours":

        # Finished games always stay at the end
        filtered_df["Finished_sort"] = (
            filtered_df["Status"]
            == STATUS_FINISHED
        )

        filtered_df = (
            filtered_df
            .sort_values(
                by=[
                    "Finished_sort",
                    "Hours"
                ],
                ascending=[
                    True,
                    ascending
                ]
            )
            .drop(
                columns=["Finished_sort"]
            )
        )

    # -----------------------------------------------------
    # Name
    # -----------------------------------------------------

    elif sort_by == "Name":

        filtered_df = (
            filtered_df
            .sort_values(
                by="Game",
                ascending=ascending,
                key=lambda column:
                    column.str.lower()
            )
        )

    # =====================================================
    # GALLERY
    # =====================================================

    # -------------------------------------------------
    # Pagination
    # -------------------------------------------------

    # If search/filter/sorting changes:
    # return to page 1
    filter_signature = (
        search_term,
        tuple(status_filters),
        sort_by,
        order
    )

    previous_filter_signature = (
        st.session_state.get(
            "gallery_filter_signature"
        )
    )

    if previous_filter_signature is None:

        st.session_state[
            "gallery_filter_signature"
        ] = filter_signature

    elif previous_filter_signature != filter_signature:

        st.session_state.gallery_page = 1

        st.session_state[
            "gallery_filter_signature"
        ] = filter_signature

    total_results = len(
        filtered_df
    )

    if total_results == 0:

        st.markdown(
            "**0 games found**"
        )

        if search_term and status_filters:

            st.info(
                "🔎 No games match your search and the selected "
                "statuses. Try changing the filters."
            )

        elif search_term:

            st.info(
                "🔎 No games match your search. "
                "Try another name."
            )

        elif status_filters:

            st.info(
                "🎮 There are no games with the selected statuses."
            )

        else:

            st.info(
                "🎮 There are no games to show."
            )

        st.stop()

    total_pages = max(
        1,
        (
            total_results
            + PAGE_SIZE
            - 1
        ) // PAGE_SIZE
    )

    if (
        st.session_state.gallery_page
        > total_pages
    ):
        st.session_state.gallery_page = (
            total_pages
        )

    current_page = (
        st.session_state.gallery_page
    )

    # -------------------------------------------------
    # Results + compact navigation
    # -------------------------------------------------

    results_col, prev_col, page_col, next_col = st.columns(
        [7.2, 0.55, 0.75, 0.55],
        vertical_alignment="center",
        gap="small"
    )

    with results_col:

        st.markdown(
            f"**{total_results} games found**"
        )

    with prev_col:

        if st.button(
            "←",
            width="stretch",
            disabled=current_page <= 1,
            key="gallery_previous_page"
        ):

            st.session_state.gallery_page -= 1
            st.rerun()

    with page_col:

        st.markdown(
            f"<div style='text-align:center; font-weight:600;'>"
            f"{current_page} / {total_pages}"
            f"</div>",
            unsafe_allow_html=True
        )

    with next_col:

        if st.button(
            "→",
            width="stretch",
            disabled=current_page >= total_pages,
            key="gallery_next_page"
        ):

            st.session_state.gallery_page += 1
            st.rerun()

    # -------------------------------------------------
    # Games on this page
    # -------------------------------------------------

    start_index = (
        current_page - 1
    ) * PAGE_SIZE

    end_index = (
        start_index
        + PAGE_SIZE
    )

    gallery_df = filtered_df.iloc[
        start_index:end_index
    ]

    # -------------------------------------------------
    # Smooth clickable covers
    # -------------------------------------------------

    game_button_css = []

    for _, css_game in gallery_df.iterrows():

        css_appid = int(
            css_game["AppID"]
        )

        css_image_url = get_game_image(
            css_appid
        )

        game_button_css.append(
            f"""
            .st-key-open_game_{css_appid} button {{
                width: 100% !important;
                min-height: 0 !important;
                height: auto !important;
                aspect-ratio: 460 / 215 !important;
                padding: 0 !important;
                border: 0 !important;
                border-radius: 8px !important;
                background-image: url("{css_image_url}") !important;
                background-size: cover !important;
                background-position: center !important;
                background-repeat: no-repeat !important;
                color: transparent !important;
                font-size: 0 !important;
                box-shadow: none !important;
                overflow: hidden !important;
            }}

            .st-key-open_game_{css_appid} button p {{
                font-size: 0 !important;
                color: transparent !important;
            }}

            .st-key-open_game_{css_appid} button:hover {{
                filter: brightness(1.06);
            }}
            """
        )

    st.markdown(
        "<style>"
        + "".join(game_button_css)
        + "</style>",
        unsafe_allow_html=True
    )

    # -------------------------------------------------
    # Gallery
    # -------------------------------------------------

    for start in range(
        0,
        len(gallery_df),
        GAMES_PER_ROW
    ):

        row_games = gallery_df.iloc[
            start:
            start + GAMES_PER_ROW
        ]

        columns = st.columns(
            GAMES_PER_ROW
        )

        for column, (_, game) in zip(
            columns,
            row_games.iterrows()
        ):

            with column:

                appid = int(
                    game["AppID"]
                )

                # ---------------------------------
                # Smooth clickable banner
                # ---------------------------------

                st.button(
                    f"Open {game['Game']}",
                    key=f"open_game_{appid}",
                    width="stretch",
                    help=str(game["Game"]),
                    on_click=open_game_dialog,
                    args=(appid,)
                )

                # ---------------------------------
                # Name
                # ---------------------------------

                display_name = shorten_game_title(
                    game["Game"]
                )

                st.markdown(
                    f"**{display_name}**"
                )

                # ---------------------------------
                # Hours
                # ---------------------------------

                st.caption(
                    f"⏱️ {game['Hours']:.1f} h"
                )

                # ---------------------------------
                # Quick status
                # ---------------------------------

                current_status = (
                    game["Status"]
                )

                if current_status in STATUSES:

                    current_index = (
                        STATUSES.index(
                            current_status
                        )
                    )

                else:

                    current_index = 0

                status_key = (
                    f"gallery_status_{appid}"
                )

                st.selectbox(
                    "Status",
                    STATUSES,
                    index=current_index,
                    key=status_key,
                    label_visibility="collapsed",
                    on_change=save_gallery_status,
                    args=(
                        appid,
                        game["Notes"],
                        status_key
                    )
                )

