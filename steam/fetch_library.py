import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import db_manager
from data.models import User, db
from steam.steam_api import get_owned_games
from utils.logging import logger


async def fetch_and_store_games_for_all_users():
    """Fetch and store games for all users with a Steam ID."""
    users = db_manager.get_all_users()
    for user in users:
        if user.steam_id:
            logger.info(f"Fetching games for user {user.id} (Steam ID: {user.steam_id})")
            await fetch_and_store_games(user.id, user.steam_id)


async def fetch_and_store_games(user_id, steam_id):
    """Fetch games for a user and store them in the database."""
    games = get_owned_games(steam_id)
    if not games:
        logger.warning(f"Could not retrieve games for user {user_id} (Steam ID: {steam_id})")
        return

    for game_data in games:
        try:
            with db.atomic():
                # Fetch detailed game info
                details = get_game_details(game_data['appid'])

                # Extract relevant details, defaulting to None if not found
                name = details.get('name', game_data['name']) if details else game_data['name']
                tags = ",".join([g['description'] for g in details.get('genres', [])]) if details and details.get('genres') else None
                release_date = details.get('release_date', {}).get('date') if details and details.get('release_date') else None
                min_players = None # Steam API does not directly provide min/max players in appdetails
                max_players = None # You might need to scrape or use another API for this
                description = details.get('short_description') if details else None

                # Add or get the game in the global Game table
                game_id = db_manager.add_game(
                    name=name,
                    steam_appid=str(game_data['appid']),
                    tags=tags,
                    min_players=min_players,
                    max_players=max_players,
                    release_date=release_date,
                    description=description
                )
                if game_id is None:
                    logger.error(f"Failed to add or retrieve game {name} to the global game list.")
                    continue

                # Link the game to the user's library
                db_manager.add_user_game(user_id, game_id, 'PC')
                logger.info(f"Stored game {name} for user {user_id}.")
        except Exception as e:
            logger.error(f"Error storing game {game_data.get('name', 'Unknown')} for user {user_id}: {e}")

    logger.info(f"Successfully stored {len(games)} games for user {user_id}.")


async def main():
    """Provide a test entry point for fetching and storing games."""
    # This is a test user. In the future, we'll get this from the database.
    test_user_id = 1
    test_steam_id = "76561198040794894"  # Replace with a real Steam ID for testing

    # Add the user to the database for testing
    try:
        User.get_or_create(id=test_user_id, discord_id="test_discord_id", steam_id=test_steam_id)
    except Exception as e:
        logger.error(f"Error adding test user: {e}")

    await fetch_and_store_games(test_user_id, test_steam_id)


if __name__ == "__main__":
    asyncio.run(main())
