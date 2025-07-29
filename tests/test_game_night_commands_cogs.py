# Standard library imports
import json
from unittest.mock import AsyncMock, MagicMock, patch

# Third-party imports
import discord
import pytest
import pytest_asyncio
from discord.ext import commands

# Local application imports
from bot.cogs.game_night_commands import GameNightCommands, WeeklyAvailabilityConfigView
from data import db_manager
from data.models import Game, GameNight, GameNightAttendee, GuildConfig, User, UserAvailability, db


@pytest_asyncio.fixture
async def mock_bot():
    """Mock the Discord bot for testing."""
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, application_id=1234567890)
    bot.scheduler = MagicMock()
    bot.logger = MagicMock() # Add mock logger
    await bot.add_cog(GameNightCommands(bot))
    return bot


@pytest.fixture
def mock_interaction():
    """Mock a Discord interaction for testing."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.message = AsyncMock() # Make interaction.message awaitable
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
    db.create_tables([User, Game, GameNight, GameNightAttendee, GuildConfig, UserAvailability])
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

@pytest.mark.asyncio
async def test_configure_weekly_slots_command(mock_bot, mock_interaction):
    """Test the /configure_weekly_slots command sends the configuration view."""
    mock_interaction.guild = MagicMock(id=123)
    cog = mock_bot.get_cog("GameNightCommands")
    await cog.configure_weekly_slots.callback(cog, mock_interaction)

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_interaction.followup.send.assert_called_once()
    args, kwargs = mock_interaction.followup.send.call_args
    assert "view" in kwargs
    view = kwargs["view"]
    assert isinstance(view, WeeklyAvailabilityConfigView)
    assert kwargs["ephemeral"] is True

@pytest.mark.asyncio
async def test_weekly_availability_config_view_load_existing_pattern(mock_bot, mock_interaction):
    """Test that WeeklyAvailabilityConfigView loads existing patterns."""
    guild_id = str(mock_interaction.guild.id)
    existing_pattern = {"0": [0, 1, 2], "1": [10, 11]}
    db_manager.set_guild_custom_availability(guild_id, json.dumps(existing_pattern))

    view = WeeklyAvailabilityConfigView(mock_bot, guild_id)
    assert view.selected_slots == {int(k): v for k, v in existing_pattern.items()}

@pytest.mark.asyncio
async def test_weekly_availability_config_view_toggle_slot(mock_bot, mock_interaction):
    """Test toggling a single slot in WeeklyAvailabilityConfigView."""
    guild_id = str(mock_interaction.guild.id)
    view = WeeklyAvailabilityConfigView(mock_bot, guild_id)
    view.message = AsyncMock()

    # Click to select a slot
    mock_interaction.data = {"custom_id": "slot_0_0"} # Monday, 12:00 AM
    await view.on_button_click(mock_interaction)
    assert 0 in view.selected_slots[0]
    mock_interaction.response.edit_message.assert_called_once()
    mock_interaction.response.edit_message.reset_mock()

    # Click again to unselect the same slot
    await view.on_button_click(mock_interaction)
    assert 0 not in view.selected_slots[0]
    mock_interaction.response.edit_message.assert_called_once()

@pytest.mark.asyncio
async def test_weekly_availability_config_view_clear_all_day(mock_bot, mock_interaction):
    """Test clearing all slots for a day."""
    guild_id = str(mock_interaction.guild.id)
    view = WeeklyAvailabilityConfigView(mock_bot, guild_id)
    view.message = AsyncMock()

    # Select all first
    view.selected_slots[0] = list(range(len(view.time_slots_labels)))

    mock_interaction.data = {"custom_id": "clear_all_0"} # Monday
    await view.on_button_click(mock_interaction)

    assert len(view.selected_slots[0]) == 0
    mock_interaction.response.edit_message.assert_called_once()

@pytest.mark.asyncio
async def test_weekly_availability_config_view_save(mock_bot, mock_interaction):
    """Test saving the configuration in WeeklyAvailabilityConfigView."""
    guild_id = str(mock_interaction.guild.id)
    view = WeeklyAvailabilityConfigView(mock_bot, guild_id)
    view.message = AsyncMock()

    # Select some slots
    view.selected_slots[0].append(0)
    view.selected_slots[0].append(1)

    mock_interaction.data = {"custom_id": "save"}
    await view.on_button_click(mock_interaction)

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_interaction.followup.send.assert_called_once_with("Your weekly availability has been saved!", ephemeral=True)

    # Verify data saved to DB
    saved_pattern_json = db_manager.get_guild_custom_availability(guild_id)
    saved_pattern = json.loads(saved_pattern_json)
    assert saved_pattern["0"] == [0, 1]

    # Verify view is disabled and stopped
    for item in view.children:
        assert item.disabled is True
    assert view.is_finished()

@pytest.mark.asyncio
async def test_weekly_availability_config_view_cancel(mock_bot, mock_interaction):
    """Test canceling the configuration in WeeklyAvailabilityConfigView."""
    guild_id = str(mock_interaction.guild.id)
    view = WeeklyAvailabilityConfigView(mock_bot, guild_id)
    view.message = AsyncMock()

    # Select some slots (should not be saved)
    view.selected_slots[0].append(0)

    mock_interaction.data = {"custom_id": "cancel"}
    await view.on_button_click(mock_interaction)

    mock_interaction.response.send_message.assert_called_once_with("Weekly availability configuration cancelled.", ephemeral=True)

    # Verify data not saved to DB
    saved_pattern_json = db_manager.get_guild_custom_availability(guild_id)
    assert saved_pattern_json is None # Should still be None or original if it existed

    # Verify view is disabled and stopped
    for item in view.children:
        assert item.disabled is True
    assert view.is_finished()
