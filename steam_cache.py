import streamlit as st

from steam_api import (
    get_owned_games,
    get_player_summary,
)


@st.cache_data(ttl=3600)
def load_games(steam_api_key, steam_id):
    return get_owned_games(
        steam_api_key,
        steam_id
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_player_summary(steam_api_key, steam_id):
    return get_player_summary(
        steam_api_key,
        steam_id
    )
