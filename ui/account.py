import json
from datetime import datetime

import streamlit as st

from constants import STATUSES
from database import (
    get_all_game_data,
    import_game_data,
)
from settings import save_settings
from steam_api import (
    get_player_summary,
    resolve_steam_id,
)
from steam_cache import (
    load_games,
    load_player_summary,
)


def _save_verified_steam_connection(
    steam_profile,
    steam_api_key
):
    """Validate the Steam account, save the configuration and clear caches."""

    resolved_steam_id = resolve_steam_id(
        steam_profile,
        steam_api_key
    )

    player = get_player_summary(
        steam_api_key,
        resolved_steam_id
    )

    save_settings(
        steam_profile=steam_profile,
        steam_id=resolved_steam_id,
        steam_api_key=steam_api_key
    )

    load_games.clear()
    load_player_summary.clear()

    return player


def clear_steam_menu():
    st.session_state.open_steam_account_dialog = False
    st.session_state.steam_menu_view = "account"

def render_backup_restore():
    """Show backup and restore options in the account menu."""

    backup_tab, restore_tab = st.tabs(
        ["📦 Backup", "📥 Restore"]
    )

    # -----------------------------------------------------
    # Backup
    # -----------------------------------------------------

    with backup_tab:

        st.caption(
            "Save the statuses and notes you changed in the app."
        )

        current_saved_data = get_all_game_data()

        backup_games = []

        for appid, game_data in current_saved_data.items():

            backup_games.append(
                {
                    "appid": appid,
                    "status": game_data["status"],
                    "notes": game_data["notes"],
                }
            )

        backup_data = {
            "version": 1,
            "created_at": datetime.now().isoformat(
                timespec="seconds"
            ),
            "games": backup_games,
        }

        backup_json = json.dumps(
            backup_data,
            indent=4,
            ensure_ascii=False
        )

        backup_filename = (
            "steamtracker_backup_"
            + datetime.now().strftime("%Y-%m-%d")
            + ".json"
        )

        st.download_button(
            label="📦 Export backup",
            data=backup_json,
            file_name=backup_filename,
            mime="application/json",
            width="stretch",
            key="account_export_backup"
        )

        st.caption(
            f"{len(backup_games)} games included in the backup."
        )

    # -----------------------------------------------------
    # Restore
    # -----------------------------------------------------

    with restore_tab:

        st.caption(
            "Restore statuses and notes from a backup."
        )

        uploaded_backup = st.file_uploader(
            "Select backup",
            type=["json"],
            label_visibility="collapsed",
            key="account_restore_file"
        )

        if st.button(
            "📥 Restore backup",
            width="stretch",
            disabled=uploaded_backup is None,
            key="account_restore_backup"
        ):

            try:

                backup = json.load(
                    uploaded_backup
                )

                if not isinstance(
                    backup,
                    dict
                ):
                    raise ValueError(
                        "The backup file is not valid."
                    )

                if backup.get("version") != 1:
                    raise ValueError(
                        "Unsupported backup version."
                    )

                games_to_import = backup.get(
                    "games"
                )

                if not isinstance(
                    games_to_import,
                    list
                ):
                    raise ValueError(
                        "The backup does not contain a valid "
                        "list of games."
                    )

                valid_games = []

                for game in games_to_import:

                    if not isinstance(
                        game,
                        dict
                    ):
                        continue

                    if "appid" not in game:
                        continue

                    if "status" not in game:
                        continue

                    status = game["status"]

                    if status not in STATUSES:
                        continue

                    try:
                        appid = int(
                            game["appid"]
                        )
                    except (TypeError, ValueError):
                        continue

                    notes = game.get(
                        "notes",
                        ""
                    )

                    if notes is None:
                        notes = ""
                    elif not isinstance(notes, str):
                        notes = str(notes)

                    valid_games.append(
                        {
                            "appid": appid,
                            "status": status,
                            "notes": notes,
                        }
                    )

                if not valid_games:
                    raise ValueError(
                        "No valid games were found "
                        "in the backup."
                    )

                imported_count = import_game_data(
                    valid_games
                )

                st.success(
                    f"Backup restored: "
                    f"{imported_count} games imported."
                )

                st.rerun()

            except Exception as error:

                st.error(
                    f"Error restoring backup: {error}"
                )

@st.dialog(
    "Steam",
    width="small",
    on_dismiss=clear_steam_menu
)
def show_steam_account(
    player,
    steam_profile,
    steam_id,
    steam_api_key
):

    menu_view = st.session_state.steam_menu_view

    # =====================================================
    # ACCOUNT
    # =====================================================

    if menu_view == "account":

        account_col1, account_col2 = st.columns(
            [1, 3],
            vertical_alignment="center"
        )

        with account_col1:

            avatar_url = player.get(
                "avatarfull"
            )

            if avatar_url:
                st.image(
                    avatar_url,
                    width=72
                )

        with account_col2:

            st.markdown(
                f"### {player.get('personaname', 'Steam')}"
            )

            st.caption(
                "✅ Steam account connected"
            )

        if st.button(
            "🔄 Refresh library",
            width="stretch",
            key="refresh_steam_library"
        ):

            try:

                with st.spinner(
                    "Synchronising with Steam..."
                ):

                    load_games.clear()

                    # Force a fresh call to Steam.
                    load_games(
                        steam_api_key,
                        steam_id
                    )

                st.session_state.library_just_refreshed = True
                st.session_state.open_steam_account_dialog = False
                st.session_state.steam_menu_view = "account"

                st.rerun()

            except Exception:

                st.error(
                    "Could not refresh the library. "
                    "Try again in a moment."
                )

        profile_url = player.get(
            "profileurl"
        )

        if profile_url:

            st.link_button(
                "↗️ View Steam profile",
                profile_url,
                width="stretch"
            )

        if st.button(
            "💾 Backup and restore",
            width="stretch",
            key="open_backup_restore"
        ):

            st.session_state.steam_menu_view = "backup"
            st.rerun()

        if st.button(
            "⚙️ Change settings",
            width="stretch",
            key="open_steam_settings"
        ):

            st.session_state.steam_menu_view = "settings"
            st.rerun()

    # =====================================================
    # BACKUP / RESTORE
    # =====================================================

    elif menu_view == "backup":

        if st.button(
            "← Back",
            key="back_from_backup"
        ):

            st.session_state.steam_menu_view = "account"
            st.rerun()

        st.markdown(
            "#### 💾 Backup and restore"
        )

        render_backup_restore()

    # =====================================================
    # CHANGE SETTINGS
    # =====================================================

    elif menu_view == "settings":

        if st.button(
            "← Back",
            key="back_from_settings"
        ):

            st.session_state.steam_menu_view = "account"
            st.rerun()

        st.markdown(
            "#### Change settings"
        )

        new_steam_profile = st.text_input(
            "Steam profile",
            value=steam_profile
        )

        st.markdown(
            "**Steam Web API Key**"
        )

        st.link_button(
            "🔑 Get / view Steam Web API Key",
            "https://steamcommunity.com/dev/apikey",
            width="stretch"
        )

        new_steam_api_key = st.text_input(
            "Steam Web API Key",
            value=steam_api_key,
            type="password"
        )

        if st.button(
            "💾 Save changes",
            type="primary",
            width="stretch",
            key="save_steam_settings"
        ):

            new_steam_profile = (
                new_steam_profile.strip()
            )

            new_steam_api_key = (
                new_steam_api_key.strip()
            )

            try:

                _save_verified_steam_connection(
                    new_steam_profile,
                    new_steam_api_key
                )

                st.session_state.steam_menu_view = "account"
                st.session_state.open_steam_account_dialog = False

                st.rerun()

            except Exception:

                st.error(
                    "Could not connect to Steam. "
                    "Check the profile and API Key."
                )


def render_onboarding():

    onboarding_left, onboarding_center, onboarding_right = (
        st.columns(
            [1.2, 2.4, 1.2]
        )
    )

    with onboarding_center:

        with st.container(
            border=True
        ):

            st.subheader(
                "👋 Connect your Steam account"
            )

            st.caption(
                "You only need to do this once. Your profile and API Key "
                "are stored only on this device."
            )

            st.divider()

            # -------------------------------------------------
            # 1. Steam profile
            # -------------------------------------------------

            st.markdown(
                "#### 1 · Steam profile"
            )

            st.caption(
                "Copy your Steam profile address "
                "and paste it below."
            )

            new_steam_profile = st.text_input(
                "Steam profile",
                placeholder=(
                    "https://steamcommunity.com/"
                    "id/your-profile/"
                ),
                label_visibility="collapsed",
                key="initial_steam_profile"
            )

            st.write("")

            # -------------------------------------------------
            # 2. API Key
            # -------------------------------------------------

            st.markdown(
                "#### 2 · Steam Web API Key"
            )

            st.caption(
                "The app uses this key to access "
                "your library directly through Steam."
            )

            st.link_button(
                "🔑 Get Steam Web API Key",
                "https://steamcommunity.com/dev/apikey",
                width="stretch"
            )

            st.caption(
                "If Steam asks for a **Domain Name**, "
                "enter `localhost`."
            )

            new_steam_api_key = st.text_input(
                "Steam Web API Key",
                type="password",
                placeholder="Paste your API Key here",
                label_visibility="collapsed",
                key="initial_steam_api_key"
            )

            st.caption(
                "🔒 The API Key is not included in app "
                "backups."
            )

            with st.expander(
                "Need help?"
            ):

                st.markdown(
                    """
                    **Steam profile**  
                    Open your Steam profile and copy the address
                    shown in your browser.

                    **API Key**  
                    Use the button above to open Steam's official page
                    and get the key.

                    **Private library**  
                    If no games appear after connecting,
                    check on Steam that **Game details**
                    are visible.
                    """
                )

            st.write("")

            # -------------------------------------------------
            # Connect to Steam
            # -------------------------------------------------

            if st.button(
                "✅ Connect to Steam",
                type="primary",
                width="stretch",
                key="initial_steam_connection"
            ):

                new_steam_profile = (
                    new_steam_profile.strip()
                )

                new_steam_api_key = (
                    new_steam_api_key.strip()
                )

                if not new_steam_profile:

                    st.error(
                        "Enter your Steam profile link."
                    )

                elif not new_steam_api_key:

                    st.error(
                        "Enter your Steam Web API Key."
                    )

                else:

                    try:

                        with st.spinner(
                            "Checking your Steam account..."
                        ):

                            verified_player = (
                                _save_verified_steam_connection(
                                    new_steam_profile,
                                    new_steam_api_key
                                )
                            )

                        st.session_state[
                            "initial_connection_success"
                        ] = verified_player.get(
                            "personaname",
                            "Steam"
                        )

                        st.rerun()

                    except ValueError:

                        st.error(
                            "Could not find that Steam profile. "
                            "Check the address and try again."
                        )

                    except Exception:

                        st.error(
                            "Could not validate the Steam account. "
                            "Check the profile and API Key, then try again."
                        )

