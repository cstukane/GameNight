import os
import sys
import unittest
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot import reminders as events  # events.py was renamed to reminders.py
from data import db_manager
from data.models import Game, GameExclusion, GameNight, GameNightAttendee, User, UserGame, db


class TestEvents(unittest.TestCase):
    """Tests for the events (reminders) module."""

    def setUp(self):
        """Set up a temporary in-memory database for each test."""
        self.db_file = f"./data/test_users_{self._testMethodName}.db"
        db.init(self.db_file)
        db.connect()
        db.create_tables([User, Game, UserGame, GameNight, GameNightAttendee, GameExclusion])

        self.organizer_id = db_manager.add_user("org_discord_id", "Organizer")
        self.channel_id = "test_channel_id"

    def tearDown(self):
        """Tear down the database and remove the temporary file."""
        db.close()
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_add_game_night_event(self):
        """Test the creation of a new game night event."""
        scheduled_time = datetime.now() + timedelta(days=1)
        poll_close_time = scheduled_time - timedelta(hours=1)
        event_id = events.add_game_night_event(self.organizer_id, scheduled_time, self.channel_id, poll_close_time)
        self.assertIsNotNone(event_id)

        event_details = events.get_game_night_details(event_id)
        self.assertIsNotNone(event_details)
        self.assertEqual(event_details.organizer.id, self.organizer_id)
        self.assertEqual(event_details.channel_id, self.channel_id)
        self.assertEqual(event_details.poll_close_time.replace(microsecond=0), poll_close_time.replace(microsecond=0))

    def test_get_upcoming_game_nights(self):
        """Test that only future game nights are retrieved as upcoming."""
        # Add an upcoming event
        upcoming_time = datetime.now() + timedelta(days=2)
        poll_close_time_upcoming = upcoming_time - timedelta(hours=1)
        events.add_game_night_event(self.organizer_id, upcoming_time, self.channel_id, poll_close_time_upcoming)

        # Add a past event
        past_time = datetime.now() - timedelta(days=2)
        poll_close_time_past = past_time - timedelta(hours=1)
        events.add_game_night_event(self.organizer_id, past_time, self.channel_id, poll_close_time_past)

        upcoming_events = events.get_upcoming_game_nights()
        self.assertEqual(len(upcoming_events), 1)
        self.assertEqual(upcoming_events[0].scheduled_time.day, upcoming_time.day)

    def test_set_attendee_status(self):
        """Test setting and updating the status of an attendee for a game night."""
        scheduled_time = datetime.now() + timedelta(days=1)
        poll_close_time = scheduled_time - timedelta(hours=1)
        event_id = events.add_game_night_event(self.organizer_id, scheduled_time, self.channel_id, poll_close_time)
        attendee_id = db_manager.add_user("attendee_discord_id", "Attendee")

        events.set_attendee_status(event_id, attendee_id, "attending")
        attendees = events.get_attendees_for_game_night(event_id)
        self.assertEqual(len(attendees), 1)
        self.assertEqual(attendees[0].status, "attending")

        events.set_attendee_status(event_id, attendee_id, "not_attending")
        attendees = events.get_attendees_for_game_night(event_id)
        self.assertEqual(len(attendees), 1)
        self.assertEqual(attendees[0].status, "not_attending")

    def test_update_game_night_poll_message_id(self):
        """Test updating the availability and game poll message IDs for an event."""
        scheduled_time = datetime.now() + timedelta(days=1)
        poll_close_time = scheduled_time - timedelta(hours=1)
        event_id = events.add_game_night_event(self.organizer_id, scheduled_time, self.channel_id, poll_close_time)

        events.update_game_night_poll_message_id(event_id, "availability", "12345")
        event_details = events.get_game_night_details(event_id)
        self.assertEqual(event_details.availability_poll_message_id, "12345")

        events.update_game_night_poll_message_id(event_id, "game", "67890")
        event_details = events.get_game_night_details(event_id)
        self.assertEqual(event_details.game_poll_message_id, "67890")


if __name__ == '__main__':
    unittest.main()
