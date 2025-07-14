from datetime import datetime

from data.models import GameNight, GameNightAttendee
from utils.logging import logger


def add_game_night_event(organizer_id, scheduled_time, channel_id, poll_close_time=None):
    """Add a new game night event to the database.

    Args:
    ----
        organizer_id (int): The database ID of the user organizing the event.
        scheduled_time (datetime): The date and time the event is scheduled for.
        channel_id (str): The Discord channel ID where the event is being held.
        poll_close_time (datetime, optional): The time the availability poll should close.

    Returns:
    -------
        int or None: The ID of the newly created game night event, or None if an error occurred.

    """
    try:
        game_night = GameNight.create(
            organizer=organizer_id,
            scheduled_time=scheduled_time,
            channel_id=channel_id,
            poll_close_time=poll_close_time
        )
        return game_night.id
    except Exception as e:
        logger.error(f"Error adding game night event: {e}")
        return None


def get_upcoming_game_nights():
    """Retrieve all upcoming game night events from the database.

    Returns
    -------
        list[GameNight]: A list of GameNight model instances, ordered by scheduled time.

    """
    try:
        return list(
            GameNight.select()
            .where(GameNight.scheduled_time > datetime.now())
            .order_by(GameNight.scheduled_time.asc())
        )
    except Exception as e:
        logger.error(f"Error getting upcoming game nights: {e}")
        return []


def set_attendee_status(game_night_id, user_id, status):
    """Set a user's attendance status for a specific game night.

    Args:
    ----
        game_night_id (int): The ID of the game night.
        user_id (int): The database ID of the user.
        status (str): The user's attendance status (e.g., 'attending', 'maybe').

    """
    try:
        GameNightAttendee.replace(game_night=game_night_id, user=user_id, status=status).execute()
    except Exception as e:
        logger.error(f"Error setting attendee status: {e}")


def get_attendees_for_game_night(game_night_id):
    """Retrieve all attendees and their status for a specific game night.

    Args:
    ----
        game_night_id (int): The ID of the game night.

    Returns:
    -------
        list[GameNightAttendee]: A list of GameNightAttendee model instances.

    """
    try:
        return list(GameNightAttendee.select().where(GameNightAttendee.game_night == game_night_id))
    except Exception as e:
        logger.error(f"Error getting attendees for game night: {e}")
        return []


def update_game_night_poll_message_id(game_night_id, poll_type, message_id):
    """Update the message ID for a specific poll type for a game night.

    Args:
    ----
        game_night_id (int): The ID of the game night.
        poll_type (str): The type of poll ('availability' or 'game').
        message_id (str): The Discord message ID of the poll.

    """
    try:
        game_night = GameNight.get_by_id(game_night_id)
        if poll_type == "availability":
            game_night.availability_poll_message_id = message_id
        elif poll_type == "game":
            game_night.game_poll_message_id = message_id
        else:
            logger.warning(f"Invalid poll_type '{poll_type}' provided.")
            return
        game_night.save()
    except GameNight.DoesNotExist:
        logger.warning(f"Game night with ID {game_night_id} not found.")
    except Exception as e:
        logger.error(f"Error updating poll message ID: {e}")


def get_game_night_details(game_night_id):
    """Retrieve details for a specific game night by its ID.

    Args:
    ----
        game_night_id (int): The ID of the game night.

    Returns:
    -------
        GameNight or None: The GameNight model instance, or None if not found.

    """
    try:
        return GameNight.get_by_id(game_night_id)
    except GameNight.DoesNotExist:
        logger.warning(f"Game night with ID {game_night_id} not found.")
        return None
    except Exception as e:
        logger.error(f"Error getting game night details: {e}")
        return None
