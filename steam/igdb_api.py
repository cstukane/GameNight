# steam/igdb_api.py

import os
import httpx # Use httpx for async requests
from utils.config import IGDB_CLIENT_ID, IGDB_CLIENT_SECRET
from utils.logging import logger

class IGDBAPI:
    """An ASYNCHRONOUS client for interacting with the IGDB API."""

    def __init__(self):
        """Initialize the IGDB API client."""
        self.base_url = "https://api.igdb.com/v4"
        self.auth_url = "https://id.twitch.tv/oauth2/token"
        self.client_id = IGDB_CLIENT_ID
        self.client_secret = IGDB_CLIENT_SECRET
        self.access_token = None
        self.headers = None

    async def _get_access_token(self):
        """Fetch a new access token from the Twitch API."""
        # This check prevents re-fetching the token on every single request
        if self.access_token:
            return self.access_token
        
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.auth_url, params=params)
                response.raise_for_status()
                token_data = response.json()
                self.access_token = token_data['access_token']
                
                # Set up the headers once we have the token
                self.headers = {
                    'Client-ID': self.client_id,
                    'Authorization': f'Bearer {self.access_token}',
                    'Accept': 'application/json',
                }
                logger.info("Successfully obtained new IGDB access token.")
                return self.access_token
            except httpx.RequestError as e:
                logger.error(f"Error getting IGDB access token: {e}")
                return None

    async def _make_request(self, endpoint, data):
        """Make a POST request to a specified IGDB API endpoint."""
        # Ensure we have a token and headers before making a request
        if not self.headers:
            await self._get_access_token()
            if not self.headers:
                logger.error("IGDB access token not available. Cannot make request.")
                return None

        url = f"{self.base_url}/{endpoint}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self.headers, data=data)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                # Log the specific error from IGDB
                logger.error(f"Error making IGDB request to {endpoint} (Query: {data}): {e}")
                logger.error(f"Response body: {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"An unexpected error occurred during IGDB request: {e}")
                return None

    # --- THIS IS THE MAIN FIXED FUNCTION ---
    async def translate_store_ids_to_igdb_ids(self, platform_name: str, external_ids: list[str]) -> set[int]:
        """
        Translates a list of external store IDs (e.g., Microsoft Store) to a set of unique IGDB game IDs.
        """
        if not external_ids:
            return set()

        platform_category_map = {
            "microsoft store": 11,
            "xbox": 11,
            "steam": 1,
        }
        category_id = platform_category_map.get(platform_name.lower())
        if not category_id:
            logger.warning(f"Unknown platform name: {platform_name}. Cannot translate IDs.")
            return set()

        all_igdb_ids = set()
        # IGDB API has a limit on query size, so we process in batches of 200.
        batch_size = 200
        for i in range(0, len(external_ids), batch_size):
            batch = external_ids[i:i + batch_size]
            
            # IGDB expects a comma-separated list of strings, like ("id1", "id2")
            formatted_ids = ", ".join([f'"{ext_id}"' for ext_id in batch])

            # The query is now correct for the /external_games endpoint
            query = (
                f'fields game.id; '
                f'where category = {category_id} & uid = ({formatted_ids}); '
                f'limit 500;' # Max limit
            )
            
            response = await self._make_request("external_games", query)
            
            if response:
                for item in response:
                    # The correct path to the ID is item['game']['id']
                    if "game" in item and "id" in item["game"]:
                        all_igdb_ids.add(item["game"]["id"])
        
        return all_igdb_ids

    async def get_game_by_igdb_id(self, igdb_id: int):
        """Fetch detailed game information from IGDB by its unique IGDB ID."""
        data = (
            f"fields name, cover.image_id, summary, multiplayer_modes.*, aggregated_rating; "
            f"where id = {igdb_id};"
        )
        return await self._make_request("games", data)

    def get_cover_url(self, image_id: str, size: str = "cover_big"):
        """Constructs the full URL for a game cover image."""
        if not image_id:
            return None
        return f"https://images.igdb.com/igdb/image/upload/t_{size}/{image_id}.jpg"

    async def search_games(self, query: str, limit: int = 5) -> list[dict]:
        """Searches for games by name using the IGDB API."""
        data = f"search \"{query}\"; fields name, cover.image_id, summary, aggregated_rating, first_release_date, multiplayer_modes.*; limit {limit};"
        response = await self._make_request("games", data)
        return response if response else []


# Initialize IGDBAPI client globally to be imported and used by other files
igdb_api = IGDBAPI()
