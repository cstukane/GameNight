import json
import os
import sys
import unittest
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Local application imports
from bot import events  # Import events for add_game_night_event
from data import database, db_manager
from data.models import (
    Game,
    GameNight,
    GameNightAttendee,
    GuildConfig,
    Poll,
    PollResponse,
    User,
    UserAvailability,
    UserGame,
    db,
)


class TestDbManager(unittest.TestCase):
    """Tests for the database manager module."""

    def setUp(self):
        """Set up a temporary database and create necessary tables."""
        self.db_file = f"./data/test_users_{self._testMethodName}.db"
        database.set_database_file(self.db_file)
        db.connect()
        db.create_tables([
            User, Game, UserGame, GameNight, GameNightAttendee,
            UserAvailability, Poll, PollResponse, GuildConfig
        ])

    def tearDown(self):
        """Close the database connection and remove the temporary database file."""
        db.close()
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_add_user(self):
        """Test adding a new user to the database."""
        user_id = db_manager.add_user("12345", "testuser")
        self.assertIsNotNone(user_id)
        user = db_manager.get_user_by_discord_id("12345")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "testuser")

    def test_set_steam_id(self):
        """Test setting the Steam ID for a user."""
        user_id = db_manager.add_user("12345", "testuser")
        db_manager.set_steam_id(user_id, "76561198000000000")
        user = db_manager.get_user_by_discord_id("12345")
        self.assertEqual(user.steam_id, "76561198000000000")

    def test_add_game(self):
        """Test adding a new game to the database."""
        game_id = db_manager.add_game(
            "Test Game", min_players=2, max_players=4,
            release_date="2023-01-01", description="A test game."
        )
        self.assertIsNotNone(game_id)
        game = db_manager.get_game_by_name("Test Game")
        self.assertIsNotNone(game)
        self.assertEqual(game.name, "Test Game")

    def test_add_user_game(self):
        """Test linking a user and a game (ownership)."""
        user_id = db_manager.add_user("123", "user1")
        game_id = db_manager.add_game("Game1", release_date="2023-01-01", description="A test game.")
        db_manager.add_user_game(user_id, game_id, "PC")
        ownerships = db_manager.get_user_game_ownerships(user_id)
        self.assertEqual(len(ownerships), 1)
        self.assertEqual(ownerships[0].game.name, "Game1")

    def test_get_games_owned_by_users(self):
        """Test retrieving games commonly owned by a list of users."""
        user1_id = db_manager.add_user("1", "user1")
        user2_id = db_manager.add_user("2", "user2")
        game1_id = db_manager.add_game("Game A")
        game2_id = db_manager.add_game("Game B")

        db_manager.add_user_game(user1_id, game1_id, "PC")
        db_manager.add_user_game(user2_id, game1_id, "PC")
        db_manager.add_user_game(user1_id, game2_id, "PC")

        common_games = db_manager.get_games_owned_by_users([user1_id, user2_id])
        self.assertEqual(len(common_games), 1)
        self.assertEqual(common_games[0].name, "Game A")

    def test_set_user_weekly_availability(self):
        """Test setting and retrieving a user's weekly availability."""
        user_id = db_manager.add_user("123", "testuser")
        db_manager.set_user_weekly_availability(user_id, "0,2,4")
        availability = db_manager.get_user_weekly_availability(user_id)
        self.assertEqual(availability, "0,2,4")

    def test_get_all_users_weekly_availability(self):
        """Test retrieving the weekly availability for all users."""
        user1_id = db_manager.add_user("1", "user1")
        user2_id = db_manager.add_user("2", "user2")
        db_manager.set_user_weekly_availability(user1_id, "0,1")
        db_manager.set_user_weekly_availability(user2_id, "2,3")
        all_avail = db_manager.get_all_users_weekly_availability()
        self.assertIn("1", all_avail)
        self.assertIn("2", all_avail)
        self.assertEqual(all_avail["1"], "0,1")
        self.assertEqual(all_avail["2"], "2,3")

    def test_create_poll(self):
        """Test creating a new poll in the database."""
        poll_id = db_manager.create_poll(
            "msg1", "chan1", "availability", datetime.now(),
            datetime.now() + timedelta(days=1), "[]", "[]"
        )
        self.assertIsNotNone(poll_id)
        poll = db_manager.get_poll_by_id(poll_id)
        self.assertIsNotNone(poll)
        self.assertEqual(poll.message_id, "msg1")

    def test_record_poll_response(self):
        """Test recording a user's response to a poll."""
        user_id = db_manager.add_user("123", "testuser")
        poll_id = db_manager.create_poll(
            "msg1", "chan1", "availability", datetime.now(),
            datetime.now() + timedelta(days=1), "[]", "[]"
        )
        db_manager.record_poll_response(poll_id, user_id, "0,1")
        responses = db_manager.get_poll_responses(poll_id)
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].selected_options, "0,1")

    def test_get_poll_response_count(self):
        """Test counting the number of responses for a poll."""
        user1_id = db_manager.add_user("1", "user1")
        user2_id = db_manager.add_user("2", "user2")
        poll_id = db_manager.create_poll(
            "msg1", "chan1", "availability", datetime.now(),
            datetime.now() + timedelta(days=1), "[]", "[]"
        )
        db_manager.record_poll_response(poll_id, user1_id, "0")
        db_manager.record_poll_response(poll_id, user2_id, "1")
        count = db_manager.get_poll_response_count(poll_id)
        self.assertEqual(count, 2)

    def test_get_expected_participant_count(self):
        """Test getting the expected number of participants for a poll."""
        user1_id = db_manager.add_user("1", "user1")
        user2_id = db_manager.add_user("2", "user2")
        expected_participants = json.dumps([str(user1_id), str(user2_id)])
        poll_id = db_manager.create_poll(
            "msg1", "chan1", "availability", datetime.now(),
            datetime.now() + timedelta(days=1), "[]", expected_participants
        )
        count = db_manager.get_expected_participant_count(poll_id)
        self.assertEqual(count, 2)

    def test_update_poll_status(self):
        """Test updating the status of a poll."""
        poll_id = db_manager.create_poll(
            "msg1", "chan1", "availability", datetime.now(),
            datetime.now() + timedelta(days=1), "[]", "[]"
        )
        db_manager.update_poll_status(poll_id, "closed")
        poll = db_manager.get_poll_by_id(poll_id)
        self.assertEqual(poll.status, "closed")

    def test_update_game_night_selected_game(self):
        """Test updating the selected game for a game night."""
        user_id = db_manager.add_user("1", "user1")
        game_id = db_manager.add_game("Test Game")
        game_night_id = events.add_game_night_event(user_id, datetime.now(), "channel1")
        db_manager.update_game_night_selected_game(game_night_id, game_id)
        game_night = events.get_game_night_details(game_night_id)
        self.assertEqual(game_night.selected_game.id, game_id)

    def test_set_and_get_guild_planning_channel(self):
        """Test setting and getting a guild's planning channel."""
        guild_id = "12345"
        channel_id = "67890"
        db_manager.set_guild_planning_channel(guild_id, channel_id)
        retrieved_channel_id = db_manager.get_guild_planning_channel(guild_id)
        self.assertEqual(retrieved_channel_id, channel_id)

    def test_set_and_get_guild_custom_availability(self):
        """Test setting and getting a guild's custom availability pattern."""
        guild_id = "guild123"
        pattern = {"0": [0, 1, 2], "1": [10, 11]}
        pattern_json = json.dumps(pattern)
        db_manager.set_guild_custom_availability(guild_id, pattern_json)
        retrieved_pattern = db_manager.get_guild_custom_availability(guild_id)
        self.assertEqual(retrieved_pattern, pattern_json)

    def test_get_user_game_night_history(self):
        """Test retrieving a user's game night attendance history."""
        user_id = db_manager.add_user("user_hist", "User History")
        game_id = db_manager.add_game("Game for History")

        # Create some game nights and attendees
        gn1_id = events.add_game_night_event(user_id, datetime(2024, 7, 10, 19, 0), "channel_hist1")
        events.set_attendee_status(gn1_id, user_id, "attending")
        db_manager.update_game_night_selected_game(gn1_id, game_id)

        gn2_id = events.add_game_night_event(user_id, datetime(2024, 7, 11, 20, 0), "channel_hist2")
        events.set_attendee_status(gn2_id, user_id, "attending")
        db_manager.update_game_night_selected_game(gn2_id, game_id)

        # User not attending
        gn3_id = events.add_game_night_event(user_id, datetime(2024, 7, 12, 21, 0), "channel_hist3")
        events.set_attendee_status(gn3_id, user_id, "not_attending")

        history = db_manager.get_user_game_night_history(user_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].id, gn2_id)  # Newest first
        self.assertEqual(history[1].id, gn1_id)

    def test_get_attended_game_nights_count(self):
        """Test counting the number of game nights a user has attended."""
        user_id = db_manager.add_user("user_count", "User Count")
        db_manager.add_game("Game for Count")

        # Game nights within the year
        gn1_id = events.add_game_night_event(user_id, datetime(2024, 1, 15, 19, 0), "channel_count1")
        events.set_attendee_status(gn1_id, user_id, "attending")

        gn2_id = events.add_game_night_event(user_id, datetime(2024, 6, 20, 20, 0), "channel_count2")
        events.set_attendee_status(gn2_id, user_id, "attending")

        # Game night outside the year
        gn3_id = events.add_game_night_event(user_id, datetime(2023, 12, 25, 21, 0), "channel_count3")
        events.set_attendee_status(gn3_id, user_id, "attending")

        # Game night not attending
        gn4_id = events.add_game_night_event(user_id, datetime(2024, 3, 10, 18, 0), "channel_count4")
        events.set_attendee_status(gn4_id, user_id, "not_attending")

        count = db_manager.get_attended_game_nights_count(user_id, datetime(2024, 1, 1), datetime(2025, 1, 1))
        self.assertEqual(count, 2)


if __name__ == '__main__':
    unittest.main()
