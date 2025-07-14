import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.automation_tasks import AutomationTasks, AvailabilityPollView
from data import db_manager


@pytest.fixture
def mock_bot():
    """Create a mock bot object for testing."""
    bot = AsyncMock(spec=commands.Bot)
    bot.user = MagicMock(id=12345)  # Mock bot's own user ID
    bot.get_channel.return_value = AsyncMock(spec=discord.TextChannel)
    bot.get_channel.return_value.send = AsyncMock()
    bot.scheduler = MagicMock()
    return bot


@pytest.fixture
def automation_tasks_cog(mock_bot):
    """Create an instance of the AutomationTasks cog with a mock bot."""
    return AutomationTasks(mock_bot)


@pytest.mark.asyncio
async def test_start_weekly_availability_poll_no_filtered_slots(automation_tasks_cog, mock_bot):
    """Test that the poll is not started if no suitable time slots are found."""
    with patch('data.db_manager.get_all_users_weekly_availability', return_value={}):
        with patch('data.db_manager.get_all_users', return_value=[]):
            await automation_tasks_cog.start_weekly_availability_poll()
            mock_bot.get_channel.return_value.send.assert_not_called()


@pytest.mark.asyncio
async def test_start_weekly_availability_poll_success(automation_tasks_cog, mock_bot):
    """Test the successful creation of a weekly availability poll."""
    mock_user = MagicMock(discord_id="123", id=1)
    mock_bot.guilds = [MagicMock(id=123456789)]  # Mock a guild

    with patch('data.db_manager.get_all_users_weekly_availability', return_value={
        "123": "0,1,2,3,4,5,6"  # User available every day
    }):
        with patch('data.db_manager.get_all_users', return_value=[mock_user]):
            with patch('data.db_manager.get_guild_planning_channel', return_value="123456789012345678"):
                with patch('data.db_manager.create_poll', return_value=1):
                    await automation_tasks_cog.start_weekly_availability_poll()
                    mock_bot.get_channel.return_value.send.assert_called_once()
                    message_mock = mock_bot.get_channel.return_value.send.return_value
                    message_mock.edit.assert_called_once()
                    args, kwargs = message_mock.edit.call_args
                    assert isinstance(kwargs['embed'], discord.Embed)
                    assert isinstance(kwargs['view'], AvailabilityPollView)
                    mock_bot.scheduler.add_job.assert_called_once()


@pytest.mark.asyncio
async def test_start_weekly_availability_poll_with_custom_pattern(automation_tasks_cog, mock_bot):
    """Test that the weekly poll correctly uses a guild's custom availability pattern."""
    mock_user = MagicMock(discord_id="123", id=1)
    mock_bot.guilds = [MagicMock(id=123456789)]  # Mock a guild

    # Define a custom availability pattern (e.g., Monday 17:00, Tuesday 18:30)
    custom_pattern = {
        "0": [34],  # Monday 17:00 (17 * 2 = 34)
        "1": [37]   # Tuesday 18:30 (18 * 2 + 1 = 37)
    }
    custom_pattern_json = json.dumps(custom_pattern)

    with patch('data.db_manager.get_guild_custom_availability', return_value=custom_pattern_json):
        with patch('data.db_manager.get_all_users_weekly_availability', return_value={
            "123": "0,1,2,3,4,5,6"  # User available every day
        }):
            with patch('data.db_manager.get_all_users', return_value=[mock_user]):
                with patch('data.db_manager.get_guild_planning_channel', return_value="123456789012345678"):
                    with patch('data.db_manager.create_poll', return_value=1) as mock_create_poll:
                        await automation_tasks_cog.start_weekly_availability_poll()

                        # Assert that create_poll was called with the correct suggested_slots_json
                        _, kwargs = mock_create_poll.call_args
                        suggested_slots_json_arg = kwargs['suggested_slots_json']
                        suggested_slots = [datetime.fromisoformat(s) for s in json.loads(suggested_slots_json_arg)]

                        # Expected slots based on custom_pattern for the next 7 days
                        expected_slots = []
                        today = datetime.now()
                        for i in range(7):
                            current_day = today + timedelta(days=i)
                            day_of_week_num = current_day.weekday()
                            if str(day_of_week_num) in custom_pattern:
                                for slot_index in custom_pattern[str(day_of_week_num)]:
                                    hour = slot_index // 2
                                    minute = 30 if slot_index % 2 == 1 else 0
                                    expected_slots.append(
                                        current_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                                    )

                        # Filter expected slots by user availability (mocked to be all days)
                        all_users_weekly_availability = db_manager.get_all_users_weekly_availability()
                        final_expected_slots = []
                        for slot in expected_slots:
                            day_of_week_num = slot.weekday()
                            is_any_user_available = False
                            for _, available_days_str in all_users_weekly_availability.items():
                                if available_days_str:
                                    available_days_nums = [
                                        int(d) for d in available_days_str.split(',')]
                                    if day_of_week_num in available_days_nums:
                                        is_any_user_available = True
                                        break
                            if is_any_user_available:
                                final_expected_slots.append(slot)

                        # Compare the generated slots with the expected slots
                        assert len(suggested_slots) == len(final_expected_slots)
                        for s1, s2 in zip(suggested_slots, final_expected_slots):
                            assert s1.replace(microsecond=0) == s2.replace(microsecond=0)

                    mock_bot.get_channel.return_value.send.assert_called_once()
                    message_mock = mock_bot.get_channel.return_value.send.return_value
                    message_mock.edit.assert_called_once()
                    args, kwargs = message_mock.edit.call_args
                    assert isinstance(kwargs['embed'], discord.Embed)
                    assert isinstance(kwargs['view'], AvailabilityPollView)
                    mock_bot.scheduler.add_job.assert_called_once()
