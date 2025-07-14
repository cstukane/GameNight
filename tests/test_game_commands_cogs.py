# Standard library imports
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Third-party imports
import discord
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands

# Local application imports
from bot.cogs.game_night_commands import GameNightCommands, WeeklyAvailabilityConfigView
from data.db_manager import Game, User
from utils.errors import GameNightError


# Mocks and Fixtures
@pytest.fixture
def mock_bot():
    """Pytest fixture for a mock bot."""
    bot = AsyncMock(spec=commands.Bot)
    bot.scheduler = AsyncMock(spec=AsyncIOScheduler)
    bot.get_channel.return_value = AsyncMock(spec=discord.TextChannel, id=1234567890)
    return bot


@pytest.fixture
def mock_interaction():
    """Pytest fixture for a mock discord Interaction."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user = AsyncMock(spec=discord.User, id="12345", display_name="TestUser")
    interaction.channel_id = 1234567890
    interaction.guild_id = 9876543210
    interaction.guild = AsyncMock(spec=discord.Guild, id=9876543210)
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.message = AsyncMock()
    return interaction


@pytest.fixture
def mock_db_manager():
    """Pytest fixture for a mock database manager."""
    with patch('bot.cogs.game_night_commands.db_manager', autospec=True) as mock:
        mock.add_user.return_value = 1
        mock.get_user_by_discord_id.return_value = User(id=1, discord_id="12345", display_name="TestUser")
        mock.get_user_weekly_availability.return_value = "Monday,Wednesday"
        yield mock


@pytest.fixture
def mock_events():
    """Pytest fixture for a mock events module."""
    with patch('bot.cogs.game_night_commands.events', autospec=True) as mock:
        mock.add_game_night_event.return_value = 101
        yield mock


@pytest.fixture
def mock_poll_manager():
    """Pytest fixture for a mock poll manager."""
    with patch('bot.cogs.game_night_commands.poll_manager', autospec=True) as mock:
        mock.create_availability_poll.return_value = AsyncMock(id=999)
        yield mock


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.WeeklyAvailabilityModal')
async def test_set_weekly_availability(mock_modal_class, mock_bot, mock_interaction, mock_db_manager):
    """Test the set_weekly_availability command."""
    cog = GameNightCommands(mock_bot)
    await cog.set_weekly_availability.callback(cog, interaction=mock_interaction)

    mock_db_manager.get_user_by_discord_id.assert_called_once_with(str(mock_interaction.user.id))
    mock_db_manager.get_user_weekly_availability.assert_called_once_with(1)

    # Check that the Modal class was instantiated correctly
    mock_modal_class.assert_called_once_with("Monday,Wednesday")

    # Check that send_modal was called with the instance of our mocked class
    mock_interaction.response.send_modal.assert_called_once_with(mock_modal_class.return_value)


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.datetime')
async def test_next_game_night_success(mock_datetime, mock_bot, mock_interaction, mock_db_manager, mock_events,
                                       mock_poll_manager):
    """Test successful scheduling of a game night."""
    # Setup
    cog = GameNightCommands(mock_bot)
    mock_datetime.strptime.side_effect = lambda d, f: datetime.strptime(d, f)
    mock_datetime.combine.side_effect = lambda d, t: datetime.combine(d, t)

    # Execute
    await cog.next_game_night.callback(cog, mock_interaction, "01/15/2023", "19:00")

    # Assert
    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    scheduled_dt = datetime(2023, 1, 15, 19, 0)
    poll_close_dt = scheduled_dt - timedelta(hours=1)
    mock_events.add_game_night_event.assert_called_once_with(
        1, scheduled_dt, str(mock_interaction.channel_id), poll_close_dt
    )
    mock_poll_manager.create_availability_poll.assert_called_once()
    mock_events.update_game_night_poll_message_id.assert_called_once_with(101, "availability", '999')
    mock_bot.scheduler.add_job.assert_called_once()
    mock_interaction.followup.send.assert_called_once()
    sent_message = mock_interaction.followup.send.call_args[0][0]
    assert 'Game night scheduled for 2023-01-15 at 19:00! Event ID: 101.' in sent_message
    expected_gcal_link = (
        'https://calendar.google.com/calendar/render?action=TEMPLATE'
        '&text=Game+Night&dates=20230115T190000/20230115T210000'
        '&details=Join+us+for+game+night!+Event+ID:+101&sf=true&output=xml'
    )
    assert expected_gcal_link in sent_message


@pytest.mark.asyncio
async def test_set_game_night_availability(mock_bot, mock_interaction, mock_db_manager, mock_events):
    """Test setting availability for a specific game night."""
    cog = GameNightCommands(mock_bot)
    game_night_id = 101
    status = "attending"

    await cog.set_game_night_availability.callback(cog, mock_interaction, game_night_id, status)

    mock_db_manager.add_user.assert_called_once_with(str(mock_interaction.user.id), mock_interaction.user.display_name)
    mock_events.set_attendee_status.assert_called_once_with(game_night_id, 1, status)
    expected_message = f"Your availability for Game Night ID {game_night_id} has been set to **{status}**."
    mock_interaction.followup.send.assert_called_once_with(expected_message)


@pytest.mark.asyncio
async def test_game_night_autocomplete(mock_bot, mock_interaction, mock_events):
    """Test autocomplete suggestions for game night IDs."""
    cog = GameNightCommands(mock_bot)
    mock_event1 = MagicMock(id=101, scheduled_time=datetime(2023, 10, 26, 18, 0))
    mock_event2 = MagicMock(id=102, scheduled_time=datetime(2023, 10, 27, 19, 0))
    mock_events.get_upcoming_game_nights.return_value = [mock_event1, mock_event2]

    choices = await cog.game_night_autocomplete(mock_interaction, "10")
    assert len(choices) == 2
    expected_name1 = f"ID: 101 - {mock_event1.scheduled_time:%Y-%m-%d at %H:%M}"
    expected_name2 = f"ID: 102 - {mock_event2.scheduled_time:%Y-%m-%d at %H:%M}"
    assert choices[0].name == expected_name1 and choices[0].value == 101
    assert choices[1].name == expected_name2 and choices[1].value == 102


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.suggest_games')
async def test_finalize_game_night_success(mock_suggest_games, mock_bot, mock_interaction, mock_db_manager,
                                           mock_events, mock_poll_manager):
    """Test successful finalization of a game night."""
    cog = GameNightCommands(mock_bot)
    game_night_id = 101

    # Setup Mocks
    mock_details = MagicMock(id=game_night_id, organizer_id=1, channel_id=str(mock_interaction.channel_id))
    mock_events.get_game_night_details.return_value = mock_details
    mock_attendees = [MagicMock(user_id=1, status="attending"), MagicMock(user_id=2, status="maybe")]
    mock_events.get_attendees_for_game_night.return_value = mock_attendees
    mock_db_manager.get_suggested_games_for_game_night.return_value = ["User Suggested Game"]

    # Correctly mock a Game object
    mock_game = MagicMock(spec=Game)
    mock_game.name = "Bot Suggested Game"
    mock_suggest_games.return_value = [mock_game]

    mock_poll_manager.create_game_selection_poll.return_value = AsyncMock(id=1000)

    await cog.finalize_game_night.callback(cog, mock_interaction, game_night_id)

    mock_events.get_game_night_details.assert_called_with(game_night_id)
    mock_poll_manager.create_game_selection_poll.assert_called_once()
    suggestions_arg = mock_poll_manager.create_game_selection_poll.call_args[0][2]
    assert "User Suggested Game" in suggestions_arg
    assert "Bot Suggested Game" in suggestions_arg
    mock_interaction.followup.send.assert_called_with(f"Game selection poll for Game Night ID {game_night_id} has been posted.")


@pytest.mark.asyncio
async def test_configure_weekly_slots(mock_bot, mock_interaction):
    """Test the configure_weekly_slots command."""
    cog = GameNightCommands(mock_bot)

    with patch('bot.cogs.game_night_commands.WeeklyAvailabilityConfigView') as mock_view_class:
        await cog.configure_weekly_slots.callback(cog, mock_interaction)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_view_class.assert_called_once_with(mock_bot, mock_interaction.guild_id)
        mock_interaction.followup.send.assert_called_once()
        assert mock_interaction.followup.send.call_args[1]['view'] == mock_view_class.return_value


# --- Tests for WeeklyAvailabilityConfigView ---

@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.db_manager.get_guild_custom_availability')
async def test_weekly_availability_config_view_init(mock_get_avail, mock_bot, mock_interaction):
    """Test the initialization of the WeeklyAvailabilityConfigView."""
    guild_id = str(mock_interaction.guild.id)
    pattern = {0: [12, 13], 1: [18]}
    mock_get_avail.return_value = json.dumps(pattern)

    view = WeeklyAvailabilityConfigView(mock_bot, guild_id)

    mock_get_avail.assert_called_once_with(guild_id)
    assert view.guild_id == guild_id
    assert view.selected_slots == pattern
    # Should have a day selector and other buttons
    assert any(isinstance(child, discord.ui.Select) and child.custom_id == "day_selector" for child in view.children)
    assert any(isinstance(child, discord.ui.Button) and child.custom_id == "save" for child in view.children)


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.db_manager.get_guild_custom_availability', return_value=None)
async def test_weekly_availability_config_view_toggle_slot(mock_get_avail, mock_bot, mock_interaction):
    """Test toggling a single slot in WeeklyAvailabilityConfigView."""
    guild_id = str(mock_interaction.guild.id)
    view = WeeklyAvailabilityConfigView(mock_bot, guild_id)
    view.message = AsyncMock()

    # Click to select a slot
    mock_interaction.data = {"custom_id": "slot_0_0"}  # Monday, 12:00 AM
    await view.on_button_click(mock_interaction)
    assert 0 in view.selected_slots[0]
    assert view.start_selection_slot[0] is None  # Verify start_selection_slot is None after single toggle
    mock_interaction.response.edit_message.assert_called_once()
    mock_interaction.response.edit_message.reset_mock()

    # Click again to unselect the same slot
    await view.on_button_click(mock_interaction)
    assert 0 not in view.selected_slots[0]
    assert view.start_selection_slot[0] is None  # Verify start_selection_slot remains None
    mock_interaction.response.edit_message.assert_called_once()


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.db_manager')
async def test_weekly_availability_config_view_save_and_cancel(mock_db_manager, mock_bot, mock_interaction):
    """Test the save and cancel buttons."""
    guild_id = str(mock_interaction.guild.id)
    mock_db_manager.get_guild_custom_availability.return_value = None

    # Test Save
    view = WeeklyAvailabilityConfigView(mock_bot, guild_id)
    view.message = mock_interaction.message
    view.selected_slots[0] = [1, 2, 3]
    mock_interaction.data = {"custom_id": "save"}

    await view.on_button_click(mock_interaction)

    mock_db_manager.set_guild_custom_availability.assert_called_once()
    saved_json = mock_db_manager.set_guild_custom_availability.call_args[0][1]
    assert json.loads(saved_json)[str(0)] == [1, 2, 3]  # Keys are strings in JSON
    mock_interaction.message.edit.assert_called_once_with(content="Weekly availability pattern saved!", view=view)
    mock_interaction.followup.send.assert_called_once_with("Your weekly availability has been saved!", ephemeral=True)
    assert view.is_finished() is True

    # Reset mocks for the next part of the test
    mock_interaction.message.edit.reset_mock()
    mock_interaction.response.send_message.reset_mock()

    # Test Cancel
    view = WeeklyAvailabilityConfigView(mock_bot, guild_id)
    view.message = mock_interaction.message
    mock_interaction.data = {"custom_id": "cancel"}

    await view.on_button_click(mock_interaction)
    mock_interaction.message.edit.assert_called_once_with(content="Weekly availability configuration cancelled.", view=view)
    mock_interaction.response.send_message.assert_called_once_with("Weekly availability configuration cancelled.", ephemeral=True)
    assert view.is_finished() is True


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.suggest_games')
async def test_handle_game_suggestion_and_poll_no_attendees(mock_suggest, mock_bot, mock_events):
    """Test that no poll is created if there are no attendees."""
    cog = GameNightCommands(mock_bot)
    channel = AsyncMock()
    game_night_id = 101
    mock_events.get_game_night_details.return_value = MagicMock()
    mock_events.get_attendees_for_game_night.return_value = [MagicMock(status="maybe")]  # No "attending"

    await cog._handle_game_suggestion_and_poll(game_night_id, channel)
    channel.send.assert_called_once_with("No users marked as attending. Cannot finalize game night.")


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.suggest_games')
async def test_handle_game_suggestion_and_poll_no_suggestions(mock_suggest, mock_bot, mock_events, mock_db_manager):
    """Test that no poll is created if no games are found."""
    cog = GameNightCommands(mock_bot)
    channel = AsyncMock()
    game_night_id = 101
    mock_events.get_game_night_details.return_value = MagicMock()
    mock_events.get_attendees_for_game_night.return_value = [MagicMock(user_id=1, status="attending")]
    mock_db_manager.get_suggested_games_for_game_night.return_value = []
    mock_suggest.return_value = []  # No suggestions

    await cog._handle_game_suggestion_and_poll(game_night_id, channel)
    channel.send.assert_called_once_with("No suitable games found for the attending group.")


@pytest.mark.asyncio
@patch('bot.cogs.game_night_commands.suggest_games')
async def test_handle_game_suggestion_and_poll_no_poll_message(mock_suggest, mock_bot, mock_events, mock_db_manager,
                                                               mock_poll_manager):
    """Test that a failure message is sent if the poll message can't be created."""
    cog = GameNightCommands(mock_bot)
    channel = AsyncMock()
    game_night_id = 101
    mock_events.get_game_night_details.return_value = MagicMock()
    mock_events.get_attendees_for_game_night.return_value = [MagicMock(user_id=1, status="attending")]
    mock_db_manager.get_suggested_games_for_game_night.return_value = ["A Game"]
    mock_suggest.return_value = []
    mock_poll_manager.create_game_selection_poll.return_value = None  # Poll creation fails

    await cog._handle_game_suggestion_and_poll(game_night_id, channel)
    channel.send.assert_called_once_with("Failed to create game selection poll.")


@pytest.mark.asyncio
async def test_finalize_game_night_not_organizer(mock_bot, mock_interaction, mock_db_manager, mock_events):
    """Test that finalize_game_night fails if the interactor is not the organizer."""
    cog = GameNightCommands(mock_bot)
    game_night_id = 101

    # Organizer is user 2, but interactor's user_id is 1
    mock_events.get_game_night_details.return_value = MagicMock(organizer_id=2)
    mock_db_manager.get_user_by_discord_id.return_value = User(
        id=1, discord_id=mock_interaction.user.id, display_name="Not Organizer"
    )

    with pytest.raises(GameNightError, match="Only the organizer can finalize this game night."):
        await cog.finalize_game_night.callback(cog, mock_interaction, game_night_id)

    mock_interaction.response.defer.assert_called_once()
    mock_events.get_game_night_details.assert_called_once_with(game_night_id)
    mock_db_manager.get_user_by_discord_id.assert_called_once_with(str(mock_interaction.user.id))


@pytest.mark.asyncio
async def test_send_scheduled_suggestion_no_users(mock_bot):
    """Test scheduled suggestion when no users are in the DB."""
    with patch('bot.cogs.game_night_commands.db_manager') as mock_db:
        mock_db.get_all_users.return_value = []
        channel = AsyncMock()
        mock_bot.get_channel.return_value = channel

        # This is not a cog method, so it's called directly
        from bot.cogs.game_night_commands import _send_scheduled_suggestion
        await _send_scheduled_suggestion(mock_bot, '12345')

        channel.send.assert_called_once_with("No users found in the database. Cannot suggest games.")
