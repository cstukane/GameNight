import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import db_manager
from data.models import User, db
from steam.steam_api import get_owned_games, get_game_details
from utils.logging import logger


async def fetch_and_store_games_for_all_users():
    """Fetch and store games for all users with a Steam ID."""
    logger.info("Starting fetch_and_store_games_for_all_users...")
    users = db_manager.get_all_users()
    if not users:
        logger.info("No users found in the database to fetch games for.")
        return
    for user in users:
        if user.steam_id:
            logger.info(f"Fetching games for user {user.username} (Discord ID: {user.discord_id}, Steam ID: {user.steam_id})")
            await fetch_and_store_games(user.id, user.steam_id)
        else:
            logger.info(f"User {user.username} (Discord ID: {user.discord_id}) does not have a Steam ID set.")


async def fetch_and_store_games(user_id, steam_id):
    """Fetch games for a user and store them in the database."""
    games = get_owned_games(steam_id)
    if not games:
        logger.warning(f"Could not retrieve games for user {user_id} (Steam ID: {steam_id}). No games returned from Steam API.")
        return
    logger.info(f"Retrieved {len(games)} games from Steam API for user {user_id} (Steam ID: {steam_id}).")

    for game_data in games:
        try:
            with db.atomic():
                # Fetch detailed game info
                details = get_game_details(game_data['appid'])

                # Add or get the game in the global Game table
                game_name = details.get('name', game_data['name']) if details else game_data['name']
                game_id = await db_manager.add_game(
                    title=game_name,
                    steam_appid=str(game_data['appid'])
                )
                if game_id is None:
                    logger.error(f"Failed to add or retrieve game {name} to the global game list.")
                    continue

                # Link the game to the user's library
                db_manager.add_user_game(user_id, game_id, 'steam')
                logger.info(f"Stored game {name} (ID: {game_id}) for user {user_id}.")
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
