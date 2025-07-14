# Standard library imports
import json
from datetime import datetime

# Third-party imports
from peewee import fn

from utils.logging import logger

# Local application imports
from .models import (
    Game,
    GameNight,
    GameNightAttendee,
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


def add_game(
    name, steam_appid=None, tags=None, min_players=None, max_players=None,
    release_date=None, description=None, last_played=None
):
    """Add a new game to the database or update its details if it already exists."""
    try:
        with db.atomic():
            defaults = {
                'steam_appid': steam_appid,
                'tags': tags,
                'min_players': min_players,
                'max_players': max_players,
                'last_played': last_played,
                'release_date': release_date,
                'description': description,
            }
            game, created = Game.get_or_create(name=name, defaults=defaults)
            if not created:
                game.steam_appid = steam_appid or game.steam_appid
                game.tags = tags or game.tags
                game.min_players = min_players or game.min_players
                game.max_players = max_players or game.max_players
                game.release_date = release_date or game.release_date
                game.description = description or game.description
                game.save()
            return game.id
    except Exception as e:
        logger.error(f"Error in add_game: {e}")
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


def add_user_game(user_id, game_id, platform):
    """Associate a game with a user on a specific platform."""
    try:
        print(f"Attempting to add user_game: user_id={user_id}, game_id={game_id}, platform={platform}")
        UserGame.get_or_create(user=user_id, game=game_id, defaults={'platform': platform})
        print(f"Successfully added user_game: user_id={user_id}, game_id={game_id}")
    except Exception as e:
        logger.error(f"Error in add_user_game: {e}")


def remove_user_game(user_id, game_id):
    """Remove a game from a user's library."""
    try:
        query = UserGame.delete().where((UserGame.user == user_id) & (UserGame.game == game_id))
        query.execute()
    except Exception as e:
        logger.error(f"Error in remove_user_game: {e}")


def set_user_game_installed(user_id, game_id, is_installed):
    """Set the installed status for a user's game."""
    try:
        query = (
            UserGame.update(is_installed=is_installed)
            .where((UserGame.user == user_id) & (UserGame.game == game_id))
        )
        query.execute()
    except Exception as e:
        logger.error(f"Error in set_user_game_installed: {e}")


def set_game_liked_status(user_id, game_id, like: bool):
    """Set the liked status for a user's game, creating the entry if it doesn't exist."""
    try:
        user_game, _ = UserGame.get_or_create(user=user_id, game=game_id)
        if like:
            user_game.liked = True
            user_game.disliked = False
        else:
            user_game.liked = False
        user_game.save()
    except Exception as e:
        logger.error(f"Error in set_game_liked_status: {e}")


def set_game_disliked_status(user_id, game_id, dislike: bool):
    """Set the disliked status for a user's game, creating the entry if it doesn't exist."""
    try:
        user_game, _ = UserGame.get_or_create(user=user_id, game=game_id)
        if dislike:
            user_game.disliked = True
            user_game.liked = False
        else:
            user_game.disliked = False
        user_game.save()
    except Exception as e:
        logger.error(f"Error in set_game_disliked_status: {e}")


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


def get_game_by_name(name):
    """Retrieve a game by its name (case-insensitive)."""
    try:
        return Game.get(fn.LOWER(Game.name) == name.lower())
    except Game.DoesNotExist:
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
        return [game.name for game in Game.select().where(Game.name.icontains(query)).limit(25)]
    except Exception as e:
        logger.error(f"Error in search_games_by_name: {e}")
        return []


def get_user_game_ownerships(user_id):
    """Retrieve all games owned by a specific user."""
    try:
        return list(UserGame.select().where(UserGame.user == user_id))
    except Exception as e:
        logger.error(f"Error in get_user_game_ownerships: {e}")
        return []


def set_steam_id(user_id, steam_id):
    """Set the Steam ID for a given user."""
    try:
        query = User.update(steam_id=steam_id).where(User.id == user_id)
        query.execute()
    except Exception as e:
        logger.error(f"Error in set_steam_id: {e}")


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
        if available_days.lower() == "none":
            availability.available_days = ""
        else:
            availability.available_days = available_days
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
    """Retrieve all users who own a specific game and the platform they own it on."""
    try:
        query = UserGame.select(User.discord_id, UserGame.platform).join(User).where(UserGame.game == game_id)
        return [(ug.user.discord_id, ug.platform) for ug in query]
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


def set_guild_planning_channel(guild_id, channel_id):
    """Set the planning channel ID for a given guild."""
    try:
        config, _ = GuildConfig.get_or_create(guild_id=guild_id)
        config.planning_channel_id = channel_id
        config.save()
    except Exception as e:
        logger.error(f"Error setting guild planning channel: {e}")


def get_guild_planning_channel(guild_id):
    """Retrieve the planning channel ID for a given guild."""
    try:
        config = GuildConfig.get_or_none(guild_id=guild_id)
        return config.planning_channel_id if config else None
    except Exception as e:
        logger.error(f"Error getting guild planning channel: {e}")
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
