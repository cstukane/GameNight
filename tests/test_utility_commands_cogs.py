from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio
from discord.ext import commands

from bot.cogs.utility_commands import UtilityCommands
from data import db_manager
from data.database import initialize_database
from data.models import User, UserAvailability, VoiceActivity, db


@pytest_asyncio.fixture
async def mock_bot():
    """Mock the Discord bot for testing."""
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, application_id=1234567890)
    cog = UtilityCommands(bot)
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
    return interaction

@pytest.fixture(autouse=True)
def setup_test_db():
    """Set up and tear down a temporary test database."""
    initialize_database()
    yield
    db.drop_tables([User, UserAvailability, VoiceActivity])
    db.close()

# --- Tests for UtilityCommands Cog ---

@pytest.mark.asyncio
async def test_ping_command(mock_bot, mock_interaction):
    """Test the /ping command."""
    cog = mock_bot.get_cog("UtilityCommands")
    await cog.ping.callback(cog, mock_interaction)
    mock_interaction.response.send_message.assert_called_once_with("Pong!")

@pytest.mark.asyncio
@patch('bot.cogs.utility_commands.fetch_and_store_games', new_callable=AsyncMock)
@patch('steam.steam_api.get_owned_games')
async def test_set_steam_id_command_valid(mock_get_owned_games, mock_fetch_and_store_games, mock_bot, mock_interaction):
    """Test the /set_steam_id command with a valid Steam ID."""
    mock_get_owned_games.return_value = {
        "game_count": 1,
        "games": [{'appid': 10, 'name': 'Counter-Strike', 'playtime_forever': 100}]
    }

    cog = mock_bot.get_cog("UtilityCommands")
    steam_id = "76561198000000000"
    await cog.set_steam_id.callback(cog, mock_interaction, steam_id=steam_id)

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_fetch_and_store_games.assert_called_once()
    mock_interaction.followup.send.assert_called_once_with(
        "Your Steam library has been successfully synced!", ephemeral=True
    )

@pytest.mark.asyncio
async def test_set_steam_id_command_invalid(mock_bot, mock_interaction):
    """Test the /set_steam_id command with an invalid Steam ID."""
    cog = mock_bot.get_cog("UtilityCommands")
    steam_id = "invalid_id"
    await cog.set_steam_id.callback(cog, mock_interaction, steam_id=steam_id)

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_interaction.followup.send.assert_called_once_with(
        "**Invalid Steam ID format.**\n"
        "Please provide your **64-bit Steam ID**, which is a 17-digit number.\n\n"
        "**How to find your Steam ID:**\n"
        "1. Go to a site like [SteamID.io](https://steamid.io/).\n"
        "2. Enter your Steam profile name or URL.\n"
        "3. Look for the value labeled **steamID64**.",
        ephemeral=True
    )

@pytest.mark.asyncio
async def test_set_weekly_availability_command(mock_bot, mock_interaction):
    """Test the /set_weekly_availability command."""
    user_id = db_manager.add_user(str(mock_interaction.user.id), mock_interaction.user.display_name)

    cog = mock_bot.get_cog("UtilityCommands")
    availability_input = "Monday,Wednesday"
    await cog.set_weekly_availability.callback(cog, mock_interaction, available_days=availability_input)

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    expected_message = f"Your weekly availability has been set to: **{availability_input}**."
    mock_interaction.followup.send.assert_called_once_with(expected_message, ephemeral=True)
    user_availability = UserAvailability.get(user=user_id)
    assert user_availability.available_days == "0,2"

@pytest.mark.asyncio
async def test_set_weekly_availability_command_clear(mock_bot, mock_interaction):
    """Test clearing weekly availability."""
    user_id = db_manager.add_user(str(mock_interaction.user.id), mock_interaction.user.display_name)
    # Set some initial availability
    UserAvailability.create(user=user_id, available_days="0,1")

    cog = mock_bot.get_cog("UtilityCommands")
    await cog.set_weekly_availability.callback(cog, mock_interaction, available_days="none")

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_interaction.followup.send.assert_called_once_with(
        "Your weekly availability has been set to: **none**.", ephemeral=True
    )
    user_availability = UserAvailability.get(user=user_id)
    assert user_availability.available_days == ""

@pytest.mark.asyncio
async def test_set_game_pass_command(mock_bot, mock_interaction):
    """Test the /set_game_pass command."""
    db_manager.add_user(str(mock_interaction.user.id), mock_interaction.user.display_name)

    cog = mock_bot.get_cog("UtilityCommands")
    await cog.set_game_pass.callback(cog, mock_interaction, has_game_pass=True)

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_interaction.followup.send.assert_called_once_with(
        "Your Game Pass status has been set to **enabled**.", ephemeral=True
    )
    user = db_manager.get_user_by_discord_id(str(mock_interaction.user.id))
    assert user.has_game_pass is True

@pytest.mark.asyncio
async def test_set_reminder_offset_command(mock_bot, mock_interaction):
    """Test the /set_reminder_offset command with a valid choice."""
    db_manager.add_user(str(mock_interaction.user.id), mock_interaction.user.display_name)

    cog = mock_bot.get_cog("UtilityCommands")

    # Simulate a choice object
    mock_choice = MagicMock(spec=discord.app_commands.Choice)
    mock_choice.name = "1 Hour 30 Minutes"
    mock_choice.value = 90

    await cog.set_reminder_offset.callback(cog, mock_interaction, offset_minutes=mock_choice)

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_interaction.followup.send.assert_called_once_with(
        f"Your default reminder offset has been set to **{mock_choice.name}**.", ephemeral=True
    )
    user = db_manager.get_user_by_discord_id(str(mock_interaction.user.id))
    assert user.default_reminder_offset_minutes == mock_choice.value

@pytest.mark.asyncio
@patch('data.db_manager.get_user_game_night_history')
async def test_game_night_history_command_with_history(mock_get_history, mock_bot, mock_interaction):
    """Test the /game_night_history command when a user has history."""
    user_id = str(mock_interaction.user.id)
    db_manager.add_user(user_id, mock_interaction.user.display_name)

    # Mock game night objects
    mock_game_night1 = MagicMock()
    mock_game_night1.scheduled_time = datetime(2024, 7, 10, 19, 0)
    mock_game_night1.selected_game = MagicMock()
    mock_game_night1.selected_game.name = "Game A"

    mock_game_night2 = MagicMock()
    mock_game_night2.scheduled_time = datetime(2024, 7, 11, 20, 0)
    mock_game_night2.selected_game = MagicMock()
    mock_game_night2.selected_game.name = "Game B"

    mock_get_history.return_value = [mock_game_night2, mock_game_night1] # Newest first

    cog = mock_bot.get_cog("UtilityCommands")
    await cog.game_night_history.callback(cog, mock_interaction, user=mock_interaction.user)

    mock_interaction.response.defer.assert_called_once()
    mock_get_history.assert_called_once_with(db_manager.get_user_by_discord_id(user_id).id)

    sent_embed = mock_interaction.followup.send.call_args[1]['embed']
    assert sent_embed.title == f"{mock_interaction.user.display_name}'s Game Night History"
    assert "**2024-07-11 08:00 PM**: Game B" in sent_embed.description
    assert "**2024-07-10 07:00 PM**: Game A" in sent_embed.description

@pytest.mark.asyncio
@patch('data.db_manager.get_user_game_night_history')
async def test_game_night_history_command_no_history(mock_get_history, mock_bot, mock_interaction):
    """Test the /game_night_history command when a user has no history."""
    user_id = str(mock_interaction.user.id)
    db_manager.add_user(user_id, mock_interaction.user.display_name)
    mock_get_history.return_value = []

    cog = mock_bot.get_cog("UtilityCommands")
    await cog.game_night_history.callback(cog, mock_interaction, user=mock_interaction.user)

    mock_interaction.response.defer.assert_called_once()
    mock_get_history.assert_called_once_with(db_manager.get_user_by_discord_id(user_id).id)

    sent_embed = mock_interaction.followup.send.call_args[1]['embed']
    assert sent_embed.title == f"{mock_interaction.user.display_name}'s Game Night History"
    assert sent_embed.description == "No game nights attended yet."

@pytest.mark.asyncio
@patch('data.db_manager.get_attended_game_nights_count')
@patch('data.models.VoiceActivity.select')
async def test_discord_wrapped_command_with_game_nights(mock_voice_activity_select, mock_get_attended_count, mock_bot, mock_interaction):
    """Test the /discord_wrapped command including game nights attended."""
    user_id = str(mock_interaction.user.id)
    db_manager.add_user(user_id, mock_interaction.user.display_name)

    # Mock VoiceActivity data
    mock_scalar = MagicMock()
    mock_scalar.side_effect = [7200, 3]  # First call returns total_seconds, second returns unique_days
    mock_voice_activity_select.return_value.where.return_value.scalar = mock_scalar
    mock_voice_activity_select.return_value.where.return_value.count.return_value = 5

    mock_get_attended_count.return_value = 4 # Simulate 4 game nights attended

    cog = mock_bot.get_cog("UtilityCommands")
    await cog.discord_wrapped.callback(cog, mock_interaction, year=2024)

    mock_interaction.response.defer.assert_called_once()
    mock_get_attended_count.assert_called_once() # Check if it was called

    sent_embed = mock_interaction.followup.send.call_args[1]['embed']
    assert sent_embed.title == f"{mock_interaction.user.display_name}'s Discord Wrapped 2024"
    assert sent_embed.fields[0].name == "Total Time in Voice"
    assert sent_embed.fields[0].value == "2.0 hours"
    assert sent_embed.fields[1].name == "Days Joined Voice"
    assert sent_embed.fields[1].value == "3 days"
    assert sent_embed.fields[2].name == "Total Joins"
    assert sent_embed.fields[2].value == "5 times"
    assert sent_embed.fields[3].name == "Game Nights Attended"
    assert sent_embed.fields[3].value == "4 nights"
