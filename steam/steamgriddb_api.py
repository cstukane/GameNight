import requests

from utils.config import STEAMGRIDDB_API_KEY
from utils.logging import logger

BASE_URL = "https://www.steamgriddb.com/api/v2"


def get_game_image(igdb_id: int, image_type: str = "grid"):
    """Fetch a game image from SteamGridDB using an IGDB ID.

    Args:
    ----
        igdb_id (int): The IGDB ID of the game.
        image_type (str): The type of image to fetch (e.g., 'grid', 'hero', 'logo', 'icon').

    Returns:
    -------
        str: The URL of the image, or None if not found or an error occurs.

    """
    if not STEAMGRIDDB_API_KEY:
        logger.warning("STEAMGRIDDB_API_KEY not set. Cannot fetch game images.")
        return None

    headers = {
        "Authorization": f"Bearer {STEAMGRIDDB_API_KEY}"
    }

    try:
        # First, search for the game by IGDB ID to get its SteamGridDB ID
        search_url = f"{BASE_URL}/games/id/{igdb_id}?type=igdb"
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        search_data = response.json()

        if not search_data.get("success") or not search_data.get("data"):
            logger.info(f"No game found on SteamGridDB for IGDB ID: {igdb_id}")
            return None

        game_id = search_data["data"]["id"]

        # Then, get the image based on SteamGridDB game ID and type
        image_url = f"{BASE_URL}/{image_type}/game/{game_id}"
        response = requests.get(image_url, headers=headers)
        response.raise_for_status()
        image_data = response.json()

        if image_data.get("success") and image_data.get("data"):
            # Return the URL of the first image found
            return image_data["data"][0]["url"]

        logger.info(f"No {image_type} image found for SteamGridDB game ID {game_id} (IGDB ID: {igdb_id}).")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching game image from SteamGridDB: {e}")
        return None
    except (KeyError, IndexError) as e:
        logger.error(f"An unexpected error occurred while processing SteamGridDB data: {e}")
        return None
