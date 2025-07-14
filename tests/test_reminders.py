# Standard library imports
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Third-party imports
import discord
import pytest
import pytest_asyncio
from discord.ext import commands

from bot import reminders

# Local application imports
from bot.cogs.game_night_commands import GameNightCommands
from data import db_manager
from data.models import Game, GameNight, GameNightAttendee, User, db


@pytest_asyncio.fixture
async def mock_bot():
    """Mock the Discord bot for testing."""
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, application_id=1234567890)
    bot.scheduler = MagicMock()
    cog = GameNightCommands(bot)
    await bot.add_cog(cog)
    return bot


@pytest.fixture
def mock_interaction():
    """Mock a Discord interaction for testing."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.user = MagicMock(id=12345, display_name="TestUser")
    interaction.channel_id = 67890
    return interaction


@pytest.fixture(autouse=True)
def setup_test_db():
    """Set up and tear down a temporary test database."""
    # Using an in-memory SQLite database for tests is fast and clean
    db.init(':memory:')
    db.connect()
    db.create_tables([User, Game, GameNight, GameNightAttendee])
    yield
    db.drop_tables([User, Game, GameNight, GameNightAttendee])
    db.close()


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.poll_manager.create_availability_poll')
@patch('bot.cogs.game_night_commands.events.update_game_night_poll_message_id')
@patch('bot.cogs.game_night_commands.events.add_game_night_event', return_value=1)
@patch('discord.ext.commands.Bot.get_channel')
async def test_next_game_night_command(
    mock_get_channel, mock_add_event, mock_update_poll_id, mock_create_poll, mock_bot, mock_interaction
):
    """Test the /next_game_night command."""
    mock_create_poll.return_value = AsyncMock(id=98765)
    mock_bot.get_channel.return_value = AsyncMock()

    cog = mock_bot.get_cog("GameNightCommands")
    await cog.next_game_night.callback(cog, mock_interaction, date="12/25/2025", time="19:00")

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_add_event.assert_called_once()
    mock_create_poll.assert_called_once()
    mock_update_poll_id.assert_called_once()
    mock_bot.scheduler.add_job.assert_called_once()
    mock_interaction.followup.send.assert_called_once()

@pytest.mark.asyncio
@patch('bot.reminders.get_game_image', return_value="http://example.com/cover.jpg")
@patch('data.db_manager.get_game_by_name')
@patch('discord.ext.commands.Bot.fetch_user')
async def test_send_game_night_reminder(mock_fetch_user, mock_get_game_by_name, mock_get_game_image, mock_bot):
    mock_user = AsyncMock()
    mock_fetch_user.return_value = mock_user
    mock_user.send = AsyncMock()

    mock_game = AsyncMock(steam_appid="12345")
    mock_get_game_by_name.return_value = mock_game

    game_name = "Test Game"
    scheduled_time = datetime.now() + timedelta(hours=1)
    user_discord_id = "123456789"
    game_night_id = 1

    await reminders.send_game_night_reminder(mock_bot, user_discord_id, game_night_id, game_name, scheduled_time)

    mock_fetch_user.assert_called_once_with(int(user_discord_id))
    mock_get_game_by_name.assert_called_once_with(game_name)
    mock_user.send.assert_called_once()
    args, kwargs = mock_user.send.call_args
    assert isinstance(kwargs['embed'], discord.Embed)
    assert "Launch Test Game on Steam" in kwargs['view'].children[0].label


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.events.set_attendee_status')
async def test_set_game_night_availability_command(
    mock_set_status, mock_bot, mock_interaction
):
    """Test the /set_game_night_availability command."""
    user_id = db_manager.add_user(str(mock_interaction.user.id), mock_interaction.user.display_name)
    game_night_id = 100

    cog = mock_bot.get_cog("GameNightCommands")
    await cog.set_game_night_availability.callback(
        cog, mock_interaction, game_night_id=game_night_id, status="attending"
    )

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_set_status.assert_called_once_with(game_night_id, user_id, "attending")
    mock_interaction.followup.send.assert_called_once_with(
        f"Your availability for Game Night ID {game_night_id} has been set to **attending**."
    )


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.GameNightCommands._handle_game_suggestion_and_poll', new_callable=AsyncMock)
@patch('bot.cogs.game_night_commands.events.get_game_night_details')
@patch('discord.ext.commands.Bot.get_channel')
async def test_finalize_game_night_command(
    mock_get_channel, mock_get_details, mock_handle_poll, mock_bot, mock_interaction
):
    """Test the /finalize_game_night command."""
    organizer_id = db_manager.add_user(str(mock_interaction.user.id), mock_interaction.user.display_name)
    game_night_id = 101

    mock_get_details.return_value = MagicMock(
        id=game_night_id, organizer_id=organizer_id, channel_id=str(mock_interaction.channel_id)
    )
    mock_bot.get_channel.return_value = AsyncMock()

    cog = mock_bot.get_cog("GameNightCommands")
    await cog.finalize_game_night.callback(cog, mock_interaction, game_night_id=game_night_id)

    mock_interaction.response.defer.assert_called_once()
    mock_get_details.assert_called_once_with(game_night_id)
    mock_handle_poll.assert_called_once()
    mock_interaction.followup.send.assert_called_once_with(
        f"Game selection poll for Game Night ID {game_night_id} has been posted."
    )
