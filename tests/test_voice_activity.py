import os
import sys
from datetime import datetime, timedelta

import pytest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.models import User, VoiceActivity, db


# Initialize the database for testing
@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    """Set up and tear down an in-memory database for the test module."""
    db.init(':memory:')  # Use in-memory database for testing
    db.connect()
    db.create_tables([User, VoiceActivity])
    yield
    db.close()


@pytest.fixture
def create_test_user():
    """Create a new user instance for a test."""
    # Use a unique discord_id for each test run
    unique_id = str(datetime.now().timestamp()).replace(".", "")
    user = User.create(discord_id=f"test_user_{unique_id}", username="TestUser")
    return user


def test_voice_activity_logging(create_test_user):
    """Test the creation of a VoiceActivity record when a user joins a channel."""
    user = create_test_user
    guild_id = "9876543210"
    channel_id = "1122334455"

    # Simulate joining a voice channel
    join_time = datetime.now()
    VoiceActivity.create(
        user=user,
        guild_id=guild_id,
        channel_id=channel_id,
        join_time=join_time
    )

    # Retrieve the activity and check
    activity = VoiceActivity.get(user=user, guild_id=guild_id, channel_id=channel_id, join_time=join_time)
    assert activity is not None
    assert activity.user == user
    assert activity.guild_id == guild_id
    assert activity.channel_id == channel_id
    assert activity.join_time == join_time
    assert activity.leave_time is None


def test_voice_activity_update_leave_time(create_test_user):
    """Test updating the leave_time for a VoiceActivity record."""
    user = create_test_user
    guild_id = "9876543210"
    channel_id = "1122334455"

    join_time = datetime.now() - timedelta(minutes=10)
    activity = VoiceActivity.create(
        user=user,
        guild_id=guild_id,
        channel_id=channel_id,
        join_time=join_time
    )

    # Simulate leaving a voice channel
    leave_time = datetime.now()
    activity.leave_time = leave_time
    activity.save()

    updated_activity = VoiceActivity.get_by_id(activity.id)
    assert updated_activity.leave_time is not None
    assert updated_activity.leave_time == leave_time


def test_discord_wrapped_calculation(create_test_user):
    """Test the calculation of voice activity statistics for a given year."""
    user = create_test_user
    guild_id = "9876543210"
    channel_id = "1122334455"
    current_year = datetime.now().year

    # Create some voice activities for the current year
    VoiceActivity.create(
        user=user,
        guild_id=guild_id,
        channel_id=channel_id,
        join_time=datetime(current_year, 1, 1, 10, 0, 0),
        leave_time=datetime(current_year, 1, 1, 10, 30, 0)  # 30 mins
    )
    VoiceActivity.create(
        user=user,
        guild_id=guild_id,
        channel_id=channel_id,
        join_time=datetime(current_year, 1, 2, 11, 0, 0),
        leave_time=datetime(current_year, 1, 2, 11, 45, 0)  # 45 mins
    )
    VoiceActivity.create(
        user=user,
        guild_id=guild_id,
        channel_id=channel_id,
        join_time=datetime(current_year, 1, 2, 12, 0, 0),
        leave_time=datetime(current_year, 1, 2, 12, 15, 0)  # 15 mins
    )
    # Activity outside the current year
    VoiceActivity.create(
        user=user,
        guild_id=guild_id,
        channel_id=channel_id,
        join_time=datetime(current_year - 1, 1, 1, 10, 0, 0),
        leave_time=datetime(current_year - 1, 1, 1, 10, 30, 0)
    )

    # Calculate total time, unique days, and total joins (mimicking discord_wrapped logic)
    total_time_seconds = 0
    unique_days = set()
    total_joins = 0

    start_date = datetime(current_year, 1, 1)
    end_date = datetime(current_year + 1, 1, 1) - timedelta(microseconds=1)

    voice_activities = VoiceActivity.select().where(
        VoiceActivity.user == user,
        VoiceActivity.join_time >= start_date,
        VoiceActivity.join_time <= end_date
    )

    for activity in voice_activities:
        if activity.leave_time:
            duration = activity.leave_time - activity.join_time
            total_time_seconds += duration.total_seconds()
            unique_days.add(activity.join_time.date())
            total_joins += 1

    assert round(total_time_seconds / 3600, 2) == round((30 + 45 + 15) / 60, 2)  # 1.5 hours
    assert len(unique_days) == 2
    assert total_joins == 3
