from datetime import datetime, timedelta

import discord

from data import db_manager
from data.models import GameNight, GameNightAttendee, User, db
from steam.steamgriddb_api import get_game_image
from utils.logging import logger


def add_game_night_event(organizer_id, scheduled_time, channel_id, poll_close_time=None):
    """Add a new game night event to the database."""
    try:
        with db.atomic():
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
    """Retrieve upcoming game night events."""
    try:
        query = (
            GameNight.select()
            .where(GameNight.scheduled_time > datetime.now())
            .order_by(GameNight.scheduled_time.asc())
        )
        return list(query)
    except Exception as e:
        logger.error(f"Error getting upcoming game nights: {e}")
        return []


def set_attendee_status(game_night_id, user_id, status):
    """Set a user's attendance status for a specific game night."""
    try:
        with db.atomic():
            GameNightAttendee.get_or_create(
                game_night=game_night_id,
                user=user_id,
                defaults={'status': status}
            )
            # If it already exists, update the status
            query = GameNightAttendee.update(status=status).where(
                (GameNightAttendee.game_night == game_night_id) &
                (GameNightAttendee.user == user_id)
            )
            query.execute()
    except Exception as e:
        logger.error(f"Error setting attendee status: {e}")


def get_attendees_for_game_night(game_night_id):
    """Retrieve attendees and their status for a specific game night."""
    try:
        query = (
            GameNightAttendee.select(User.discord_id, User.username, GameNightAttendee.status)
            .join(User)
            .where(GameNightAttendee.game_night == game_night_id)
        )
        return list(query)
    except Exception as e:
        logger.error(f"Error getting attendees for game night: {e}")
        return []


def update_game_night_poll_message_id(game_night_id, poll_type, message_id):
    """Update the message ID for a specific poll type for a game night."""
    try:
        game_night = GameNight.get_by_id(game_night_id)
        if poll_type == "availability":
            game_night.availability_poll_message_id = message_id
        elif poll_type == "game":
            game_night.game_poll_message_id = message_id
        else:
            logger.warning("Invalid poll_type provided.")
            return
        game_night.save()
    except GameNight.DoesNotExist:
        logger.warning(f"Game night with ID {game_night_id} not found.")
    except Exception as e:
        logger.error(f"Error updating poll message ID: {e}")


def get_game_night_details(game_night_id):
    """Retrieve details for a specific game night by its ID."""
    try:
        return GameNight.get_by_id(game_night_id)
    except GameNight.DoesNotExist:
        logger.warning(f"Game night with ID {game_night_id} not found.")
        return None
    except Exception as e:
        logger.error(f"Error getting game night details: {e}")
        return None


async def send_game_night_reminders(bot):
    """Check for upcoming game nights and send reminders based on user preferences."""
    upcoming_game_nights = get_upcoming_game_nights()
    for game_night in upcoming_game_nights:
        # Fetch all attendees for the game night
        attendees = GameNightAttendee.select().where(GameNightAttendee.game_night == game_night.id)

        for attendee in attendees:
            user = User.get_or_none(User.id == attendee.user.id)
            if not user:
                logger.warning(f"User {attendee.user.id} not found for game night {game_night.id}.")
                continue

            reminder_offset = timedelta(minutes=user.default_reminder_offset_minutes)
            reminder_time = game_night.scheduled_time - reminder_offset

            # Check if reminder time is in the near future and if reminder hasn't been sent
            # (Need a mechanism to track if reminder was sent to avoid spamming)
            if datetime.now() >= reminder_time and datetime.now() < game_night.scheduled_time:
                try:
                    discord_user = await bot.fetch_user(int(user.discord_id))
                    if discord_user:
                        reminder_msg = (
                            f"Hey {user.username}! Just a reminder: Game night is in "
                            f"{user.default_reminder_offset_minutes} minutes! "
                            f"It starts at {game_night.scheduled_time.strftime('%Y-%m-%d %H:%M')}"
                        )
                        await discord_user.send(reminder_msg)
                    else:
                        logger.warning(f"Could not find Discord user {user.discord_id} for reminder.")
                except Exception as e:
                    logger.error(f"Error sending reminder to user {user.discord_id}: {e}")


async def send_game_night_reminder(bot, user_discord_id, game_night_id, game_name, scheduled_time):
    """Send a specific reminder to a user for a scheduled game night.

    This function creates a rich embed with game details, cover art, and a launch
    button for Steam games, then sends it as a direct message to the user.

    Args:
    ----
        bot (commands.Bot): The instance of the Discord bot.
        user_discord_id (str): The Discord ID of the user to remind.
        game_night_id (int): The ID of the game night event.
        game_name (str): The name of the game being played.
        scheduled_time (datetime): The scheduled start time of the game night.

    """
    logger.info(f"Sending game night reminder to {user_discord_id} for game night {game_night_id}")
    user = await bot.fetch_user(int(user_discord_id))
    if not user:
        logger.warning(f"Could not find Discord user {user_discord_id} for reminder.")
        return

    embed = discord.Embed(
        title=f"Game Night Reminder: {game_name}!",
        description=f"Game night is about to start! It's scheduled for {scheduled_time.strftime('%I:%M %p')}.",
        color=discord.Color.blue()
    )

    # Add game art
    cover_art_url = get_game_image(game_name, image_type="hero")
    if cover_art_url:
        embed.set_image(url=cover_art_url)

    # Add launch button if it's a Steam game
    game_db = db_manager.get_game_by_name(game_name)
    if game_db and game_db.steam_appid:
        launch_url = f"steam://run/{game_db.steam_appid}"
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=f"Launch {game_name} on Steam", url=launch_url))
        await user.send(embed=embed, view=view)
    else:
        await user.send(embed=embed)
