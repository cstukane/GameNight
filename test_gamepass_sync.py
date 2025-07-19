# enrich_game_database.py
import asyncio
import json
import os
import sys
from datetime import datetime

# This is crucial for making sure the script can find your other project files
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data import db_manager
from data.database import initialize_database
from steam.igdb_api import igdb_api
from utils.logging import logger

# --- CONFIGURATION ---
# How long to wait between each game processed to avoid hitting API rate limits.
# IGDB's limit is 4 requests/sec. 1 second is very safe.
DELAY_BETWEEN_REQUESTS = 1


async def enrich_database():
    """
    A one-time script to enrich the central 'Game' table with data from IGDB.
    It translates Steam AppIDs to IGDB IDs and fetches missing details like
    cover art, descriptions, and more.
    """
    logger.info("--- Starting Game Database Enrichment Script ---")

    # 1. Connect to the database
    initialize_database()
    logger.info("Database initialized.")

    # 2. Fetch all games from the central Game table
    all_games = db_manager.get_all_games()
    if not all_games:
        logger.info("No games found in the database. Nothing to do.")
        return

    logger.info(f"Found {len(all_games)} games to process.")
    updated_count = 0

    # 3. Iterate through each game
    for index, game in enumerate(all_games):
        logger.info(f"Processing game {index + 1}/{len(all_games)}: '{game.title}' (IGDB ID: {game.igdb_id}, Steam AppID: {game.steam_appid})")

        current_igdb_id = game.igdb_id

        # 3a. If a game has a steam_appid but no igdb_id, try to translate it
        if game.steam_appid and not current_igdb_id:
            logger.info(f"Attempting to translate Steam AppID {game.steam_appid} to IGDB ID...")
            try:
                # We use the existing function with the 'steam' platform
                translated_ids = await igdb_api.translate_store_ids_to_igdb_ids(
                    platform_name="steam",
                    external_ids=[str(game.steam_appid)] # The function expects a list of strings
                )
                if translated_ids:
                    # The function returns a set, so we get the first item
                    current_igdb_id = translated_ids.pop()
                    logger.info(f"Successfully translated to IGDB ID: {current_igdb_id}")
                else:
                    logger.warning(f"Could not translate Steam AppID {game.steam_appid}.")
            except Exception as e:
                logger.error(f"An error occurred during translation for {game.title}: {e}")

        # 3b. If we have an IGDB ID (either original or newly translated), fetch details
        if current_igdb_id:
            try:
                game_data_list = await igdb_api.get_game_by_igdb_id(current_igdb_id)

                if game_data_list:
                    game_data = game_data_list[0] # The API returns a list with one item

                    # 3c. Update the game's entry in the database
                    # We use add_game because it also functions as an updater
                    db_manager.add_game(
                        igdb_id=current_igdb_id,
                        steam_appid=game.steam_appid, # Preserve original Steam AppID
                        title=game_data.get('name', game.title),
                        cover_url=igdb_api.get_cover_url(game_data.get('cover', {}).get('image_id')),
                        description=game_data.get('summary'),
                        multiplayer_info=json.dumps(game_data.get('multiplayer_modes')) if game_data.get('multiplayer_modes') else None,
                        release_date=datetime.fromtimestamp(game_data['first_release_date']).strftime('%Y-%m-%d') if 'first_release_date' in game_data else None,
                        # Min/max players are complex; we'll stick to these for now
                    )
                    logger.info(f"Successfully updated '{game.title}' with new data.")
                    updated_count += 1
                else:
                    logger.warning(f"No data returned from IGDB for ID {current_igdb_id}.")

            except Exception as e:
                logger.error(f"An error occurred fetching details for IGDB ID {current_igdb_id}: {e}", exc_info=True)
        else:
            logger.info(f"Skipping detail fetch for '{game.title}' as it has no IGDB ID.")

        # 3d. Wait to avoid hitting rate limits
        logger.info(f"Waiting for {DELAY_BETWEEN_REQUESTS} second(s)...")
        await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

    logger.info(f"--- Enrichment Script Finished. Processed {len(all_games)} games and updated {updated_count}. ---")


if __name__ == "__main__":
    asyncio.run(enrich_database())
