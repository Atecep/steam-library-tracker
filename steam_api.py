import requests

from urllib.parse import urlparse


BASE_API_URL = "https://api.steampowered.com"


def resolve_steam_id(
    profile_input,
    api_key
):
    """
    Accepts:
    - SteamID64
    - https://steamcommunity.com/profiles/7656.../
    - https://steamcommunity.com/id/nome/
    - plain vanity name

    Always returns a SteamID64.
    """

    profile_input = str(
        profile_input
    ).strip()

    api_key = str(
        api_key
    ).strip()

    if not profile_input:
        raise ValueError(
            "Enter a Steam profile."
        )

    if not api_key:
        raise ValueError(
            "Enter a Steam Web API Key."
        )

    # -----------------------------------------------------
    # Direct SteamID64
    # -----------------------------------------------------

    if (
        profile_input.isdigit()
        and len(profile_input) == 17
    ):
        return profile_input

    # -----------------------------------------------------
    # Prepare URL or vanity name
    # -----------------------------------------------------

    vanity_name = None

    if "steamcommunity.com" in profile_input.lower():

        url = profile_input

        if not url.startswith(
            ("http://", "https://")
        ):
            url = "https://" + url

        parsed = urlparse(url)

        path_parts = [
            part
            for part in parsed.path.split("/")
            if part
        ]

        if len(path_parts) < 2:
            raise ValueError(
                "The Steam profile link does not appear to be valid."
            )

        profile_type = path_parts[0].lower()
        profile_value = path_parts[1]

        # URL /profiles/STEAMID64
        if profile_type == "profiles":

            if (
                profile_value.isdigit()
                and len(profile_value) == 17
            ):
                return profile_value

            raise ValueError(
                "The SteamID in the link does not appear to be valid."
            )

        # URL /id/VANITY
        if profile_type == "id":

            vanity_name = profile_value

        else:

            raise ValueError(
                "That Steam profile format is not recognised."
            )

    else:

        # You can also enter just:
        # atecep
        vanity_name = profile_input.strip("/")

    # -----------------------------------------------------
    # Resolve Vanity URL
    # -----------------------------------------------------

    url = (
        f"{BASE_API_URL}/"
        "ISteamUser/ResolveVanityURL/v1/"
    )

    response = requests.get(
        url,
        params={
            "key": api_key,
            "vanityurl": vanity_name,
            "url_type": 1,
        },
        timeout=15
    )

    response.raise_for_status()

    data = response.json().get(
        "response",
        {}
    )

    steam_id = data.get(
        "steamid"
    )

    success = data.get(
        "success"
    )

    if success != 1 or not steam_id:

        message = data.get(
            "message",
            "Steam profile not found."
        )

        raise ValueError(
            message
        )

    return steam_id


def get_player_summary(
    api_key,
    steam_id
):
    """
    Gets basic profile information.
    Also used to validate the API key + SteamID.
    """

    url = (
        f"{BASE_API_URL}/"
        "ISteamUser/GetPlayerSummaries/v2/"
    )

    response = requests.get(
        url,
        params={
            "key": api_key,
            "steamids": steam_id,
        },
        timeout=15
    )

    response.raise_for_status()

    players = (
        response.json()
        .get("response", {})
        .get("players", [])
    )

    if not players:
        raise ValueError(
            "Could not find that Steam profile."
        )

    return players[0]


def get_owned_games(
    api_key,
    steam_id
):
    """
    Gets the user's Steam library.
    """

    url = (
        f"{BASE_API_URL}/"
        "IPlayerService/GetOwnedGames/v0001/"
    )

    params = {
        "key": api_key,
        "steamid": steam_id,
        "format": "json",
        "include_appinfo": 1,
        "include_played_free_games": 1,
    }

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    return (
        data
        .get("response", {})
        .get("games", [])
    )