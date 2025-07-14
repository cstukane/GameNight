import os
import sys
import unittest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data import db_manager
from data.models import Game, User, db


class TestDbSanity(unittest.TestCase):
    """A basic sanity check for the database connection and simple operations."""

    def setUp(self):
        """Set up a temporary, in-memory database for testing."""
        import tempfile
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        db.init(self.temp_db_file)
        db.connect()
        db.create_tables([User, Game])

    def tearDown(self):
        """Close the database connection and remove the temporary file."""
        db.close()
        os.unlink(self.temp_db_file)

    def test_add_user_and_retrieve(self):
        """Test that a user can be added and then retrieved correctly."""
        discord_id = "123456789"
        username = "TestUser"
        user_id = db_manager.add_user(discord_id, username)
        self.assertIsNotNone(user_id)

        retrieved_user = db_manager.get_user_by_discord_id(discord_id)
        self.assertIsNotNone(retrieved_user)
        self.assertEqual(retrieved_user.discord_id, discord_id)
        self.assertEqual(retrieved_user.username, username)

    def test_add_game_and_retrieve(self):
        """Test that a game can be added and then retrieved correctly."""
        game_name = "Test Game"
        game_id = db_manager.add_game(game_name)
        self.assertIsNotNone(game_id)

        retrieved_game = db_manager.get_game_by_name(game_name)
        self.assertIsNotNone(retrieved_game)
        self.assertEqual(retrieved_game.name, game_name)

if __name__ == '__main__':
    unittest.main()
