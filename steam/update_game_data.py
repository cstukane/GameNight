import asyncio
import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import db_manager
from data.models import Game, UserGame, db # Import necessary models
from steam.igdb_api import igdb_api
from utils.logging import logger

async def update_all_game_details_and_deduplicate():
    """Fetches and updates game details from IGDB for all games in the database, and de-duplicates them."""
    logger.info("Starting update and de-duplication of all game details from IGDB...")
    games_to_process = list(Game.select()) # Get all games before starting modifications
    updated_count = 0
    deduplicated_count = 0

    for game in games_to_process:
        original_game_id = game.igdb_id # Store original ID for comparison
        igdb_id_to_use = game.igdb_id

        try:
            # Step 1: Determine the best IGDB ID for this game
            if not igdb_id_to_use and game.steam_appid:
                logger.info(f"Attempting to translate Steam App ID {game.steam_appid} for '{game.title}' to IGDB ID.")
                translated_ids = await igdb_api.translate_store_ids_to_igdb_ids(
                    platform_name="steam",
                    external_ids=[str(game.steam_appid)]
                )
                if translated_ids:
                    igdb_id_to_use = list(translated_ids)[0]
                    logger.info(f"Translated '{game.title}' (Steam App ID: {game.steam_appid}) to IGDB ID: {igdb_id_to_use}")
                else:
                    logger.warning(f"Could not translate Steam App ID {game.steam_appid} for '{game.title}' to IGDB ID.")

            if not igdb_id_to_use and game.title: # If still no IGDB ID, try fuzzy matching
                logger.info(f"Attempting to resolve canonical IGDB ID for '{game.title}' using fuzzy matching.")
                resolved_id = await db_manager._resolve_canonical_igdb_id(game.title)
                if resolved_id:
                    igdb_id_to_use = resolved_id
                    logger.info(f"Resolved '{game.title}' to canonical IGDB ID: {igdb_id_to_use}")
                else:
                    logger.warning(f"Could not resolve canonical IGDB ID for '{game.title}'.")

            if not igdb_id_to_use:
                logger.warning(f"No IGDB ID or Steam App ID available for '{game.title}'. Skipping detail update and de-duplication.")
                continue

            # Step 2: Fetch comprehensive IGDB data for the determined IGDB ID
            game_data_list = await igdb_api.get_game_by_igdb_id(igdb_id_to_use)
            if not game_data_list:
                logger.warning(f"No IGDB data found for IGDB ID: {igdb_id_to_use} ('{game.title}'). Skipping detail update and de-duplication.")
                continue
            game_data = game_data_list[0]

            # Step 3: Handle de-duplication and update game details
            with db.atomic():
                existing_canonical_game = Game.get_or_none(Game.igdb_id == igdb_id_to_use)

                if existing_canonical_game and existing_canonical_game.igdb_id != original_game_id:
                    # Case A: A canonical game entry already exists, and this is a duplicate
                    logger.info(f"De-duplicating '{game.title}' (ID: {original_game_id}) into existing canonical game '{existing_canonical_game.title}' (ID: {existing_canonical_game.igdb_id}).")
                    # Update UserGame entries to point to the canonical game
                    UserGame.update(game=existing_canonical_game.igdb_id).where(UserGame.game == original_game_id).execute()
                    # Delete the duplicate game entry
                    game.delete_instance()
                    deduplicated_count += 1
                else:
                    # Case B: This game is either already canonical, or it becomes the new canonical entry
                    # Update the game's primary key if it needs to become canonical
                    if game.igdb_id != igdb_id_to_use:
                        logger.info(f"Updating '{game.title}' (ID: {game.igdb_id}) to new canonical IGDB ID: {igdb_id_to_use}.")
                        # This is tricky with Peewee and primary keys. A common pattern is to:
                        # 1. Create a new game entry with the canonical ID and updated details.
                        # 2. Re-point UserGame entries to the new ID.
                        # 3. Delete the old entry.
                        # For simplicity and to avoid potential data loss, we'll try to update in place if possible,
                        # but if the PK changes, it's safer to re-create and re-point.
                        # Given that igdb_id is the PK, we must re-create if it changes.

                        # Create a new canonical game entry with updated details
                        new_game_data = {
                            'igdb_id': igdb_id_to_use,
                            'title': game_data.get("name", game.title),
                            'steam_appid': game.steam_appid, # Keep original steam_appid
                            'cover_url': igdb_api.get_cover_url(game_data["cover"]["image_id"]) if "cover" in game_data and "image_id" in game_data["cover"] else None,
                            'description': game_data.get("summary"),
                            'metacritic': int(game_data["aggregated_rating"]) if "aggregated_rating" in game_data else None,
                            'multiplayer_info': json.dumps(game_data["multiplayer_modes"]) if "multiplayer_modes" in game_data else None,
                            'release_date': datetime.fromtimestamp(game_data["first_release_date"]).strftime('%Y-%m-%d') if "first_release_date" in game_data else None,
                            'min_players': (game_data["multiplayer_modes"][0].get("splitscreen_minimum") or game_data["multiplayer_modes"][0].get("offline_minimum") or game_data["multiplayer_modes"][0].get("online_minimum")) if "multiplayer_modes" in game_data and game_data["multiplayer_modes"] else None,
                            'max_players': (game_data["multiplayer_modes"][0].get("splitscreen_maximum") or game_data["multiplayer_modes"][0].get("offline_maximum") or game_data["multiplayer_modes"][0].get("online_maximum")) if "multiplayer_modes" in game_data and game_data["multiplayer_modes"] else None,
                        }
                        # Use get_or_create to avoid issues if it was created by another process
                        canonical_game, created_new = Game.get_or_create(igdb_id=igdb_id_to_use, defaults=new_game_data)

                        if not created_new: # If it already existed, update its details
                            for key, value in new_game_data.items():
                                if key != 'igdb_id' and value is not None: # Don't update PK, only update if value is not None
                                    setattr(canonical_game, key, value)
                            canonical_game.save()

                        # Re-point UserGame entries to the new canonical game
                        UserGame.update(game=canonical_game.igdb_id).where(UserGame.game == original_game_id).execute()
                        # Delete the old game entry
                        if original_game_id != canonical_game.igdb_id: # Only delete if it's truly a different entry
                            Game.get(Game.igdb_id == original_game_id).delete_instance()
                            deduplicated_count += 1
                        updated_count += 1
                    else:
                        # If the IGDB ID is already correct, just update details in place
                        game.title = game_data.get("name", game.title)
                        game.cover_url = igdb_api.get_cover_url(game_data["cover"]["image_id"]) if "cover" in game_data and "image_id" in game_data["cover"] else None
                        game.description = game_data.get("summary")
                        game.metacritic = int(game_data["aggregated_rating"]) if "aggregated_rating" in game_data else None
                        game.multiplayer_info = json.dumps(game_data["multiplayer_modes"]) if "multiplayer_modes" in game_data else None
                        game.release_date = datetime.fromtimestamp(game_data["first_release_date"]).strftime('%Y-%m-%d') if "first_release_date" in game_data else None
                        if "multiplayer_modes" in game_data and game_data["multiplayer_modes"]:
                            mp_modes = game_data["multiplayer_modes"][0]
                            game.min_players = mp_modes.get("splitscreen_minimum") or mp_modes.get("offline_minimum") or mp_modes.get("online_minimum")
                            game.max_players = mp_modes.get("splitscreen_maximum") or mp_modes.get("offline_maximum") or mp_modes.get("online_maximum")
                        game.save()
                        updated_count += 1

        except Exception as e:
            logger.error(f"Error processing game '{game.title}' (Original ID: {original_game_id}): {e}", exc_info=True)

        # Be kind to the API - add a small delay
        await asyncio.sleep(0.1) # 100 ms delay

    logger.info(f"Finished updating and de-duplicating game details. Total games updated: {updated_count}, de-duplicated: {deduplicated_count}.")

async def main():
    """Main entry point for the update script."""
    db_manager.db.connect()
    await update_all_game_details_and_deduplicate()
    db_manager.db.close()

if __name__ == "__main__":
    asyncio.run(main())