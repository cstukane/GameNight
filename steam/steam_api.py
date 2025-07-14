import requests

from utils.config import STEAM_API_KEY
from utils.logging import logger


def get_owned_games(steam_id):
    """Fetch the owned games of a Steam user.

    Args:
    ----
        steam_id: The 64-bit Steam ID of the user.

    Returns:
    -------
        A list of game objects, or None if the request fails.

    """
    url = (
        f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
        f"?key={STEAM_API_KEY}&steamid={steam_id}&format=json&include_appinfo=true"
    )
    try:
        response = requests.get(url)
        logger.info(f"Steam API response status code: {response.status_code}")
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()
        if not data.get('response') or not data['response'].get('games'):
            logger.warning("Steam API response is missing 'games' data. This could be due to a private profile.")
            return None
        return data['response']['games']
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        if response.status_code == 401:
            logger.error("Unauthorized: This may be due to an invalid Steam API key.")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching owned games: {e}")
        return None


def get_game_details(appid):
    """Fetch details for a specific game from the Steam API."""
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data and data[str(appid)]["success"]:
            return data[str(appid)]["data"]
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching game details from Steam: {e}")
        return None
