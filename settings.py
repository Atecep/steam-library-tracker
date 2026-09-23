import json
import os

from app_paths import CONFIG_PATH, ensure_data_dir


def load_settings():

    default_settings = {
        "steam_profile": "",
        "steam_id": "",
        "steam_api_key": "",
    }

    if not CONFIG_PATH.exists():
        return default_settings

    try:

        with CONFIG_PATH.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

    except (
        json.JSONDecodeError,
        OSError,
    ):
        return default_settings

    steam_id = str(
        data.get(
            "steam_id",
            ""
        )
    ).strip()

    steam_profile = str(
        data.get(
            "steam_profile",
            ""
        )
    ).strip()

    # Compatibility with the previous version
    if not steam_profile and steam_id:

        steam_profile = (
            "https://steamcommunity.com/"
            f"profiles/{steam_id}/"
        )

    return {
        "steam_profile": steam_profile,
        "steam_id": steam_id,

        "steam_api_key": str(
            data.get(
                "steam_api_key",
                ""
            )
        ).strip(),
    }


def save_settings(
    steam_profile,
    steam_id,
    steam_api_key
):

    ensure_data_dir()

    data = {
        "steam_profile": str(
            steam_profile
        ).strip(),

        "steam_id": str(
            steam_id
        ).strip(),

        "steam_api_key": str(
            steam_api_key
        ).strip(),
    }

    with CONFIG_PATH.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4
        )

    try:

        os.chmod(
            CONFIG_PATH,
            0o600
        )

    except OSError:
        pass