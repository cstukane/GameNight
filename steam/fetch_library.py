import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import db_manager
from data.models import Game, User, UserGame, db
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
                game, created = Game.get_or_create(
                    steam_appid=str(game_data['appid']),
                    defaults={'name': game_data['name']}
                )
                if not created:
                    game.name = game_data['name']
                    game.save()

                UserGame.get_or_create(user=user_id, game=game.id, platform='PC')
        except Exception as e:
            logger.error(f"Error storing game {game_data.get('name', 'Unknown')}: {e}")

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
