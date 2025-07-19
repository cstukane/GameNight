# Standard library imports
import json
import re
from datetime import datetime

# Third-party imports
from peewee import fn

# --- NEW IMPORTS ADDED HERE ---
from steam.igdb_api import igdb_api
from utils.logging import logger

# Local application imports
from .models import (
    Game,
    GameNight,
    GameNightAttendee,
    GamePassGame,
    GameVote,
    GuildConfig,
    Poll,
    PollResponse,
    User,
    UserAvailability,
    UserGame,
    db,
)


def add_user(discord_id, username, steam_id=None):
    """Add a new user to the database or update an existing one."""
    try:
        with db.atomic():
            user, created = User.get_or_create(
                discord_id=discord_id,
                defaults={'username': username, 'steam_id': steam_id, 'is_active': True}
            )
            if not created:
                user.username = username
                if steam_id is not None:
                    user.steam_id = steam_id
                user.is_active = True
                user.save()
            return user.id
    except Exception as e:
        logger.error(f"Error in add_user: {e}")
        return None


async def add_game(
    title=None, igdb_id=None, steam_appid=None, tags=None, min_players=None, max_players=None,
    release_date=None, description=None, last_played=None, metacritic=None, cover_url=None, multiplayer_info=None
):
    """Add a new game to the database or update its details if it already exists."""
    try:
        with db.atomic():
            # If we have an IGDB ID, fetch the game data first
            if igdb_id and not title:
                game_data_list = await igdb_api.get_game_by_igdb_id(igdb_id)
                if game_data_list:
                    game_data = game_data_list[0]
                    title = game_data.get("name")
                    if "cover" in game_data and "image_id" in game_data["cover"]:
                        cover_url = igdb_api.get_cover_url(game_data["cover"]["image_id"])
                    if "summary" in game_data:
                        description = game_data["summary"]
                    if "multiplayer_modes" in game_data:
                        multiplayer_info = json.dumps(game_data["multiplayer_modes"])
                    if "aggregated_rating" in game_data:
                        metacritic = int(game_data["aggregated_rating"])
                    if "first_release_date" in game_data:
                        release_date = datetime.fromtimestamp(game_data["first_release_date"]).strftime('%Y-%m-%d')
                    if "multiplayer_modes" in game_data:
                        # Assuming the first multiplayer mode entry has min/max players
                        if game_data["multiplayer_modes"] and len(game_data["multiplayer_modes"]) > 0:
                            min_players = game_data["multiplayer_modes"][0].get("splitscreen_minimum") or game_data["multiplayer_modes"][0].get("offline_minimum") or game_data["multiplayer_modes"][0].get("online_minimum")
                            max_players = game_data["multiplayer_modes"][0].get("splitscreen_maximum") or game_data["multiplayer_modes"][0].get("offline_maximum") or game_data["multiplayer_modes"][0].get("online_maximum")

            # In your models.py, igdb_id is the primary key for Game, so we prioritize it.
            if igdb_id:
                # If an IGDB ID is provided, use it directly.
                pass
            elif steam_appid:
                # Try to translate Steam App ID to IGDB ID
                translated_igdb_ids = await igdb_api.translate_store_ids_to_igdb_ids(
                    platform_name="steam",
                    external_ids=[str(steam_appid)]
                )
                if translated_igdb_ids:
                    igdb_id = list(translated_igdb_ids)[0] # Take the first one if multiple
                else:
                    logger.warning(f"Could not translate Steam App ID {steam_appid} for {title} to IGDB ID.")

            # If no IGDB ID yet, try to resolve it using fuzzy matching on the title
            if not igdb_id and title:
                resolved_id = await _resolve_canonical_igdb_id(title)
                if resolved_id:
                    logger.info(f"Resolved canonical IGDB ID for '{title}' to {resolved_id}")
                    igdb_id = resolved_id
                else:
                    logger.warning(f"Could not resolve canonical IGDB ID for '{title}'.")

            # If we still don't have an IGDB ID, we cannot proceed with adding/updating the game.
            if not igdb_id:
                logger.error(f"Cannot add game '{title}': No IGDB ID could be determined.")
                return None

            # Now that we have an IGDB ID, get or create the game.
            game, created = Game.get_or_create(
                igdb_id=igdb_id,
                defaults={'title': title, 'steam_appid': steam_appid}
            )

            # If we have an IGDB ID (either from input or translated), fetch details and cover
            if igdb_id:
                game_data_list = await igdb_api.get_game_by_igdb_id(igdb_id)
                if game_data_list:
                    game_data = game_data_list[0]
                    if not title: # Only update title if it wasn't provided
                        game.title = game_data.get("name", title)
                    if "cover" in game_data and "image_id" in game_data["cover"]:
                        cover_url = igdb_api.get_cover_url(game_data["cover"]["image_id"])
                        game.cover_url = cover_url
                    if "summary" in game_data:
                        game.description = game_data["summary"]
                    if "multiplayer_modes" in game_data:
                        game.multiplayer_info = json.dumps(game_data["multiplayer_modes"])
                    if "aggregated_rating" in game_data:
                        game.metacritic = int(game_data["aggregated_rating"])
                    if "first_release_date" in game_data:
                        game.release_date = datetime.fromtimestamp(game_data["first_release_date"]).strftime('%Y-%m-%d')
                    if "multiplayer_modes" in game_data:
                        # Assuming the first multiplayer mode entry has min/max players
                        if game_data["multiplayer_modes"] and len(game_data["multiplayer_modes"]) > 0:
                            game.min_players = game_data["multiplayer_modes"][0].get("splitscreen_minimum") or game_data["multiplayer_modes"][0].get("offline_minimum") or game_data["multiplayer_modes"][0].get("online_minimum")
                            game.max_players = game_data["multiplayer_modes"][0].get("splitscreen_maximum") or game_data["multiplayer_modes"][0].get("offline_maximum") or game_data["multiplayer_modes"][0].get("online_maximum")
                    # Add other fields as needed from IGDB data

            # Update fields only if they are provided
            if title is not None: game.title = title
            if steam_appid is not None: game.steam_appid = steam_appid
            if tags is not None: game.tags = tags
            if min_players is not None: game.min_players = min_players
            if max_players is not None: game.max_players = max_players
            if release_date is not None: game.release_date = release_date
            if description is not None: game.description = description
            if last_played is not None: game.last_played = last_played
            if metacritic is not None: game.metacritic = metacritic
            if cover_url is not None: game.cover_url = cover_url
            if multiplayer_info is not None: game.multiplayer_info = multiplayer_info
            game.save()

            return game
    except Exception as e:
        logger.error(f"Error in add_game for '{title}': {e}")
        return None


def mark_game_played(game_id):
    """Update the last_played timestamp for a given game."""
    try:
        game = Game.get_by_id(game_id)
        game.last_played = datetime.now()
        game.save()
    except Game.DoesNotExist:
        logger.warning(f"Game with ID {game_id} not found for marking as played.")
    except Exception as e:
        logger.error(f"Error in mark_game_played: {e}")


def add_user_game(user_id, game_id, source):
    """Associate a game with a user on a specific source platform."""
    try:
        # This will create the link only if the user doesn't already have
        # this exact game from this exact source.
        UserGame.get_or_create(user=user_id, game=game_id, source=source.upper())
    except Exception as e:
        logger.debug(f"Could not add UserGame link (might already exist): {e}")


def get_game_pass_catalog():
    """Retrieve the entire Game Pass catalog from the database."""
    logger.debug("Attempting to retrieve Game Pass catalog from database.")
    try:
        return list(GamePassGame.select(GamePassGame.microsoft_store_id, GamePassGame.title))
    except Exception as e:
        logger.error(f"Error getting game pass catalog: {e}")
        return []


def add_game_pass_game(title, microsoft_store_id):
    """Add a new Game Pass game to the database or update its details if it already exists."""
    try:
        with db.atomic():
            game, created = GamePassGame.get_or_create(
                microsoft_store_id=microsoft_store_id,
                defaults={'title': title}
            )
            if not created:
                game.title = title
                game.save()
            return game.id
    except Exception as e:
        logger.error(f"Error in add_game_pass_game for '{title}': {e}")
        return None

async def _resolve_canonical_igdb_id(game_title: str) -> int | None:
    """
    Resolves the most canonical IGDB ID for a given game title using fuzzy matching.
    Prioritizes exact matches and shorter, more general titles.
    """
    search_results = await igdb_api.search_games(game_title, limit=10)

    if not search_results:
        return None

    # Normalize titles for comparison (lowercase, remove common suffixes)
    def normalize_title(title: str) -> str:
        title = title.lower()
        # Remove common edition suffixes
        suffixes = [
            "edition", "deluxe", "ultimate", "gold", "silver", "collectors",
            "complete", "game of the year", "goty", "remastered", "hd",
            "definitive", "anniversary", "vr"
        ]
        for suffix in suffixes:
            title = re.sub(r'\s+' + re.escape(suffix) + r'\b', '', title)
        # Remove non-alphanumeric characters and extra spaces
        title = re.sub(r'[^a-z0-9]+', ' ', title).strip()
        return title

    normalized_query = normalize_title(game_title)

    best_match_id = None
    best_match_score = -1

    for result in search_results:
        if "name" not in result: # Skip results without a name
            continue

        normalized_result_name = normalize_title(result["name"])

        # Prioritize exact matches of normalized titles
        if normalized_result_name == normalized_query:
            # If an exact match, and it's shorter or equal length, it's a strong candidate
            if best_match_id is None or len(result["name"]) <= len(search_results[best_match_score]["name"] if best_match_score != -1 else float('inf')):
                best_match_id = result["id"]
                best_match_score = 100 # High score for exact normalized match
                # If we find an exact normalized match that's also the shortest, we can often stop early
                if len(result["name"]) == len(game_title): # Original titles are exact match
                    return best_match_id
                continue

        # Simple substring matching for now, can be improved with more advanced fuzzy logic
        # Consider results that contain the query title, and prefer shorter ones
        if normalized_query in normalized_result_name:
            score = len(normalized_query) / len(normalized_result_name) # Higher score for closer match
            if score > best_match_score:
                best_match_score = score
                best_match_id = result["id"]

    return best_match_id

# --- NEW CENTRAL SYNC FUNCTION ADDED HERE ---
async def sync_user_game_pass_library(user_id: int, has_game_pass: bool):
    """
    Synchronizes a user's library with the Game Pass catalog.
    Adds games if has_game_pass is True, removes their 'game_pass' sourced games if False.
    This is the central "intermediary" function you wanted.
    """
    logger.info(f"Syncing Game Pass library for user ID {user_id}. Status: {has_game_pass}")

    if not has_game_pass:
        # User has disabled Game Pass, so remove all their 'game_pass' source games.
        # This will not touch their games from 'steam' or other sources.
        query = UserGame.delete().where(
            (UserGame.user == user_id) &
            (UserGame.source == 'game_pass')
        )
        deleted_rows = query.execute()
        logger.info(f"Removed {deleted_rows} Game Pass games from user ID {user_id}'s library.")
        return

    # User has enabled Game Pass, so we add the games.
    # 1. Get the raw list of games from our Game Pass catalog table.
    game_pass_catalog = get_game_pass_catalog()
    if not game_pass_catalog:
        logger.warning("Game Pass catalog is empty. Cannot sync library.")
        return

    microsoft_store_ids = {game.microsoft_store_id for game in game_pass_catalog if game.microsoft_store_id}

    # 2. Translate those raw IDs to our canonical IGDB IDs.
    try:
        game_pass_igdb_ids = await igdb_api.translate_store_ids_to_igdb_ids(
            platform_name="Microsoft Store",
            external_ids=list(microsoft_store_ids)
        )
        logger.info(f"Translated to {len(game_pass_igdb_ids)} unique IGDB IDs for Game Pass.")
    except Exception as e:
        logger.error(f"Failed to translate Microsoft Store IDs to IGDB IDs during sync: {e}")
        return

    # 3. Add each game to the user's library.
    games_added_count = 0
    for igdb_id in game_pass_igdb_ids:
        # First, ensure the game exists in our main 'Game' table.
        game_obj = get_game_by_igdb_id(igdb_id)
        if not game_obj:
            # If it's a new game to our system, fetch its details from IGDB and add it.
            game_data_list = await igdb_api.get_game_by_igdb_id(igdb_id)
            if game_data_list:
                game_data = game_data_list[0]
                cover_url = igdb_api.get_cover_url(game_data.get("cover", {}).get("image_id")) if game_data.get("cover") else None

                # Use our existing add_game function to create it in the central 'Game' table
                game_obj = await add_game(
                    igdb_id=igdb_id,
                    title=game_data.get("name", "Unknown Title"),
                    cover_url=cover_url
                )
            else:
                logger.warning(f"Could not fetch IGDB data for ID {igdb_id}. Skipping.")
                continue # Skip to next game if data can't be fetched

        if game_obj: # Ensure game_obj is not None after potential creation
            # Now that we know the game is in the 'Game' table, link it to the user
            # with the 'game_pass' source.
            # get_or_create is perfect here. It will only create the link if
            # this user doesn't already have this game from the 'game_pass' source.
            _, created = UserGame.get_or_create(
                user=user_id,
                game=game_obj.igdb_id,
                source='game_pass'
            )
            if created:
                games_added_count += 1

    logger.info(f"Added/verified {games_added_count} new Game Pass games to user ID {user_id}'s library.")


def get_users_with_gamepass():
    """Retrieve all users who have the has_game_pass flag set to True."""
    try:
        return list(User.select().where(User.has_game_pass == True))
    except Exception as e:
        logger.error(f"Error in get_users_with_gamepass: {e}")
        return []


def remove_user_game(user_id, game_id, source=None):
    """Remove ownership records for a game from a user's library, optionally by source."""
    try:
        query = UserGame.delete().where((UserGame.user == user_id) & (UserGame.game == game_id))
        if source:
            query = query.where(UserGame.source == source)
        query.execute()
    except Exception as e:
        logger.error(f"Error in remove_user_game: {e}")

def remove_user_game_by_source(user_id: int, game_igdb_id: int, source: str):
    """Remove a specific game ownership record for a user based on game ID and source."""
    try:
        with db.atomic():
            normalized_source = source.upper()
            logger.info(f"Attempting to remove game {game_igdb_id} for user {user_id} with normalized source {normalized_source}.")
            # Find the specific UserGame entry
            user_game_entry = UserGame.get_or_none(
                (UserGame.user == user_id) &
                (UserGame.game == game_igdb_id) &
                (UserGame.source == normalized_source)
            )
            if user_game_entry:
                user_game_entry.delete_instance()
                logger.info(f"Successfully removed game {game_igdb_id} for user {user_id} from source {source}.")
            else:
                logger.warning(f"No matching game ownership found for user {user_id}, game {game_igdb_id}, source {source}. Check parameters.")
    except Exception as e:
        logger.error(f"Error in remove_user_game_by_source for user {user_id}, game {game_igdb_id}, source {source}: {e}")

def set_user_game_installed(user_id, game_id, is_installed):
    """Set the installed status for all of a user's copies of a game."""
    try:
        query = (
            UserGame.update(is_installed=is_installed)
            .where((UserGame.user == user_id) & (UserGame.game == game_id))
        )
        query.execute()
    except Exception as e:
        logger.error(f"Error in set_user_game_installed: {e}")


def set_user_game_like_dislike_status(user_id, game_id, liked: bool, disliked: bool):
    """Set the liked and disliked status for a user's game, affecting all owned platforms."""
    try:
        query = (
            UserGame.update(liked=liked, disliked=disliked)
            .where((UserGame.user == user_id) & (UserGame.game == game_id))
        )
        query.execute()
    except Exception as e:
        logger.error(f"Error in set_user_game_like_dislike_status: {e}")


def get_user_by_discord_id(discord_id):
    """Retrieve a user by their Discord ID."""
    try:
        return User.get_or_none(User.discord_id == discord_id)
    except Exception as e:
        logger.error(f"Error in get_user_by_discord_id: {e}")
        return None


def get_all_users():
    """Retrieve all active users from the database."""
    try:
        return list(User.select().where(User.is_active))
    except Exception as e:
        logger.error(f"Error in get_all_users: {e}")
        return []


def get_users_with_xbox_tokens():
    """Retrieve all users who have an Xbox refresh token."""
    try:
        return list(User.select().where(User.xbox_refresh_token.is_null(False)))
    except Exception as e:
        logger.error(f"Error in get_users_with_xbox_tokens: {e}")
        return []


def get_game_by_name(name):
    """Retrieve a game by its name (case-insensitive)."""
    try:
        return Game.get(fn.LOWER(Game.title) == name.lower())
    except Game.DoesNotExist:
        return None


def get_game_by_igdb_id(igdb_id):
    """Retrieve a game by its IGDB ID."""
    try:
        return Game.get_or_none(Game.igdb_id == igdb_id)
    except Exception as e:
        logger.error(f"Error in get_game_by_igdb_id: {e}")
        return None


def get_game_details(game_id):
    """Retrieve details for a specific game."""
    try:
        return Game.get_by_id(game_id)
    except Game.DoesNotExist:
        return None


def search_games_by_name(query):
    """Search for games by name, useful for autocomplete."""
    if not query:
        return []
    try:
        # Based on your Game model, the field is 'title'
        return list(Game.select().where(Game.title ** f'%{query}%').limit(25))
    except Exception as e:
        logger.error(f"Error in search_games_by_name: {e}")
        return []


def get_user_game_ownerships(user_id, gamepass_filter='include'):
    """Retrieve all games owned by a specific user."""
    try:
        query = UserGame.select().where(UserGame.user == user_id)
        if gamepass_filter == 'only':
            query = query.where(UserGame.source == 'game_pass')
        elif gamepass_filter == 'exclude':
            query = query.where(UserGame.source != 'game_pass')
        return list(query)
    except Exception as e:
        logger.error(f"Error in get_user_game_ownerships: {e}")
        return []


def set_steam_id(user_id, steam_id):
    """Set the Steam ID for a given user."""
    try:
        logger.info(f"Attempting to set Steam ID {steam_id} for user {user_id}.")
        query = User.update(steam_id=steam_id).where(User.id == user_id)
        rows_updated = query.execute()
        if rows_updated > 0:
            logger.info(f"Successfully set Steam ID {steam_id} for user {user_id}.")
        else:
            logger.warning(f"Could not set Steam ID {steam_id} for user {user_id}. User not found or no change.")
    except Exception as e:
        logger.error(f"Error in set_steam_id for user {user_id} with Steam ID {steam_id}: {e}")


def set_xbox_tokens(user_id, refresh_token, xuid):
    """Set the Xbox refresh token and XUID for a given user."""
    try:
        query = User.update(xbox_refresh_token=refresh_token, xbox_xuid=xuid).where(User.id == user_id)
        query.execute()
    except Exception as e:
        logger.error(f"Error in set_xbox_tokens: {e}")


def set_user_reminder_offset(user_id, offset_minutes):
    """Set the reminder offset for a given user."""
    try:
        query = User.update(default_reminder_offset_minutes=offset_minutes).where(User.id == user_id)
        query.execute()
    except Exception as e:
        logger.error(f"Error in set_user_reminder_offset: {e}")


def set_user_game_pass_status(user_id, has_game_pass: bool):
    """Set a user's Game Pass status."""
    try:
        query = User.update(has_game_pass=has_game_pass).where(User.id == user_id)
        query.execute()
    except Exception as e:
        logger.error(f"Error in set_user_game_pass_status: {e}")


def get_games_owned_by_users(user_ids):
    """Retrieve games owned by ALL users in a list."""
    if not user_ids:
        return []
    try:
        return list(
            Game.select()
            .join(UserGame)
            .where(UserGame.user.in_(user_ids))
            .group_by(Game.id)
            .having(fn.COUNT(UserGame.user.distinct()) == len(user_ids))
        )
    except Exception as e:
        logger.error(f"Error in get_games_owned_by_users: {e}")
        return []


def add_game_night_event(organizer_id, scheduled_time, channel_id):
    """Add a new game night event to the database."""
    try:
        game_night = GameNight.create(
            organizer=organizer_id,
            scheduled_time=scheduled_time,
            channel_id=channel_id
        )
        return game_night.id
    except Exception as e:
        logger.error(f"Error in add_game_night_event: {e}")
        return None


def add_suggested_game_to_game_night(game_night_id, game_name):
    """Add a game to the suggested games list for a game night."""
    try:
        game_night = GameNight.get_by_id(game_night_id)
        suggested_games = game_night.suggested_games_list.split(',') if game_night.suggested_games_list else []
        if game_name not in suggested_games:
            suggested_games.append(game_name)
            game_night.suggested_games_list = ','.join(suggested_games)
            game_night.save()
            return True
        return False
    except GameNight.DoesNotExist:
        return False
    except Exception as e:
        logger.error(f"Error in add_suggested_game_to_game_night: {e}")
        return False


def get_suggested_games_for_game_night(game_night_id):
    """Retrieve the list of user-suggested games for a game night."""
    try:
        game_night = GameNight.get_by_id(game_night_id)
        return game_night.suggested_games_list.split(',') if game_night.suggested_games_list else []
    except GameNight.DoesNotExist:
        return []
    except Exception as e:
        logger.error(f"Error in get_suggested_games_for_game_night: {e}")
        return []


def get_all_games():
    """Retrieve all games from the database."""
    try:
        return list(Game.select())
    except Exception as e:
        logger.error(f"Error getting all games: {e}")
        return []


def get_user_game_ownership(user_id, game_id):
    """Retrieve a single UserGame entry for a user and game."""
    try:
        return UserGame.get_or_none((UserGame.user == user_id) & (UserGame.game == game_id))
    except Exception as e:
        logger.error(f"Error getting user game ownership: {e}")
        return None


def set_user_weekly_availability(user_id, available_days: str):
    """Set a user's weekly availability."""
    try:
        availability, _ = UserAvailability.get_or_create(user=user_id)
        availability.available_days = "" if available_days.lower() == "none" else available_days
        availability.save()
    except Exception as e:
        logger.error(f"Error setting user weekly availability: {e}")


def get_user_weekly_availability(user_id):
    """Retrieve a user's weekly availability."""
    try:
        availability = UserAvailability.get_or_none(user=user_id)
        return availability.available_days if availability else ""
    except Exception as e:
        logger.error(f"Error getting user weekly availability: {e}")
        return ""


def get_all_users_weekly_availability():
    """Retrieve all users' weekly availability as a dict."""
    try:
        query = UserAvailability.select().join(User)
        return {avail.user.discord_id: avail.available_days for avail in query}
    except Exception as e:
        logger.error(f"Error getting all users weekly availability: {e}")
        return {}


def get_game_owners_with_platforms(game_id):
    """
    Retrieve all users who own a specific game, including their username.

    This also includes the source they own it on.
    """
    try:
        query = (
            UserGame.select(User.discord_id, User.username, UserGame.source)
            .join(User)
            .where(UserGame.game == game_id)
        )
        return [(ug.user.discord_id, ug.user.username, ug.source) for ug in query]
    except Exception as e:
        logger.error(f"Error getting game owners with platforms: {e}")
        return []


def get_attended_game_nights_count(user_id, start_date, end_date):
    """Get the count of game nights a user attended within a given date range."""
    try:
        count = GameNightAttendee.select().join(GameNight).where(
            (GameNightAttendee.user == user_id) &
            (GameNightAttendee.status == 'attending') &
            (GameNight.scheduled_time >= start_date) &
            (GameNight.scheduled_time < end_date)
        ).count()
        return count
    except Exception as e:
        logger.error(f"Error getting attended game nights count: {e}")
        return 0


def create_poll(
    poll_message_id, channel_id, poll_type, start_time, end_time,
    suggested_slots_json, expected_participants_json, related_game_night_id=None
):
    """Create a new poll entry in the database."""
    try:
        poll = Poll.create(
            message_id=poll_message_id, channel_id=channel_id, poll_type=poll_type,
            start_time=start_time, end_time=end_time,
            suggested_slots_json=suggested_slots_json,
            expected_participants_json=expected_participants_json,
            related_game_night=related_game_night_id
        )
        return poll.id
    except Exception as e:
        logger.error(f"Error creating poll: {e}")
        return None


def get_poll_response_count(poll_id):
    """Get the number of responses for a given poll."""
    try:
        return PollResponse.select().where(PollResponse.poll == poll_id).count()
    except Exception as e:
        logger.error(f"Error getting poll response count: {e}")
        return 0


def get_expected_participant_count(poll_id):
    """Get the number of expected participants for a given poll."""
    try:
        poll = Poll.get_by_id(poll_id)
        if poll and poll.expected_participants_json:
            return len(json.loads(poll.expected_participants_json))
        return None
    except Poll.DoesNotExist:
        return None
    except Exception as e:
        logger.error(f"Error getting expected participant count: {e}")
        return None


def get_poll_by_id(poll_id):
    """Retrieve a poll by its database ID."""
    try:
        return Poll.get_by_id(poll_id)
    except Poll.DoesNotExist:
        return None


def record_poll_response(poll_id, user_id, selected_options):
    """Record a user's response to a poll."""
    try:
        response, _ = PollResponse.get_or_create(poll=poll_id, user=user_id)
        response.selected_options = selected_options
        response.save()
    except Exception as e:
        logger.error(f"Error recording poll response: {e}")


def get_poll_responses(poll_id):
    """Retrieve all responses for a given poll."""
    try:
        return list(PollResponse.select().where(PollResponse.poll == poll_id))
    except Exception as e:
        logger.error(f"Error getting poll responses: {e}")
        return []


def get_poll_response(poll_id, user_id):
    """Retrieve a specific user's response for a given poll."""
    try:
        return PollResponse.get_or_none(poll=poll_id, user=user_id)
    except Exception as e:
        logger.error(f"Error getting specific poll response: {e}")
        return None


def get_game_votes(game_night_id):
    """Retrieve all game votes for a given game night."""
    try:
        return list(GameVote.select().where(GameVote.game_night == game_night_id))
    except Exception as e:
        logger.error(f"Error getting game votes: {e}")
        return []


def update_poll_status(poll_id, status):
    """Update the status of a poll."""
    try:
        query = Poll.update(status=status).where(Poll.id == poll_id)
        query.execute()
    except Exception as e:
        logger.error(f"Error updating poll status: {e}")


def update_game_night_selected_game(game_night_id, game_id):
    """Update the selected game for a game night."""
    try:
        query = GameNight.update(selected_game=game_id).where(GameNight.id == game_night_id)
        query.execute()
    except Exception as e:
        logger.error(f"Error updating game night selected game: {e}")


def set_guild_main_channel(guild_id, channel_id):
    """Set the main channel ID for a given guild."""
    try:
        config, _ = GuildConfig.get_or_create(guild_id=guild_id)
        config.main_channel_id = channel_id
        config.save()
    except Exception as e:
        logger.error(f"Error setting guild main channel: {e}")


def get_guild_main_channel(guild_id):
    """Retrieve the main channel ID for a given guild."""
    try:
        config = GuildConfig.get_or_none(guild_id=guild_id)
        return config.main_channel_id if config else None
    except Exception as e:
        logger.error(f"Error getting guild main channel: {e}")
        return None


def get_user_game_night_history(user_id):
    """Retrieve a user's game night attendance history."""
    try:
        return list(
            GameNight.select()
            .join(GameNightAttendee)
            .where(
                (GameNightAttendee.user == user_id) &
                (GameNightAttendee.status == 'attending')
            )
            .order_by(GameNight.scheduled_time.desc())
        )
    except Exception as e:
        logger.error(f"Error getting user game night history: {e}")
        return []


def set_guild_custom_availability(guild_id, pattern_json):
    """Set the custom availability pattern for a given guild."""
    try:
        config, _ = GuildConfig.get_or_create(guild_id=guild_id)
        config.custom_availability_pattern = pattern_json
        config.save()
    except Exception as e:
        logger.error(f"Error setting guild custom availability: {e}")


def get_guild_custom_availability(guild_id):
    """Retrieve the custom availability pattern for a given guild."""
    try:
        config = GuildConfig.get_or_none(guild_id=guild_id)
        return config.custom_availability_pattern if config else None
    except Exception as e:
        logger.error(f"Error getting guild custom availability: {e}")
        return None

def set_user_voice_notifications(user_id, enabled: bool):
    """Set whether a user receives voice activity notifications."""
    try:
        query = User.update(receive_voice_notifications=enabled).where(User.id == user_id)
        query.execute()
    except Exception as e:
        logger.error(f"Error setting user voice notifications: {e}")

def get_user_voice_notifications(user_id):
    """Retrieve whether a user receives voice activity notifications."""
    try:
        user = User.get_or_none(User.id == user_id)
        return user.receive_voice_notifications if user else True # Default to True if user not found
    except Exception as e:
        logger.error(f"Error getting user voice notifications: {e}")
        return True

def set_guild_voice_notification_channel(guild_id, channel_id):
    """Set the voice activity notification channel for a given guild."""
    try:
        config, _ = GuildConfig.get_or_create(guild_id=guild_id)
        config.voice_notification_channel_id = channel_id
        config.save()
    except Exception as e:
        logger.error(f"Error setting guild voice notification channel: {e}")

def get_guild_voice_notification_channel(guild_id):
    """Retrieve the voice activity notification channel for a given guild."""
    try:
        config = GuildConfig.get_or_none(guild_id=guild_id)
        return config.voice_notification_channel_id if config else None
    except Exception as e:
        logger.error(f"Error getting guild voice notification channel: {e}")
        return None
