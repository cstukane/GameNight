import os
import sys
import unittest
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot import game_suggester
from data import database, db_manager
from data.database import initialize_database  # New import
from data.models import Game, db


class TestGameSuggester(unittest.TestCase):
    """Tests for the game suggester module."""

    def setUp(self):
        """Set up a temporary database and populate it with test data."""
        self.db_file = f"./data/test_users_{self._testMethodName}.db"
        database.set_database_file(self.db_file)
        initialize_database() # Use the centralized initialization

        # Add some test users and games
        self.user1_id = db_manager.add_user("1", "User1")
        self.user2_id = db_manager.add_user("2", "User2")
        self.user3_id = db_manager.add_user("3", "User3")

        db_manager.add_game(
            "Game A", min_players=2, max_players=4, tags="strategy,coop",
            release_date="2023-01-01", description="Desc A"
        )
        db_manager.add_game(
            "Game B", min_players=3, max_players=5, tags="action,rpg",
            release_date="2023-01-01", description="Desc B"
        )
        db_manager.add_game(
            "Game C", min_players=2, max_players=2, tags="puzzle",
            release_date="2023-01-01", description="Desc C"
        )
        db_manager.add_game(
            "Game D", min_players=4, max_players=6, tags="strategy",
            release_date="2023-01-01", description="Desc D"
        )

        self.game1 = db_manager.get_game_by_name("Game A")
        self.game2 = db_manager.get_game_by_name("Game B")
        self.game3 = db_manager.get_game_by_name("Game C")
        self.game4 = db_manager.get_game_by_name("Game D")

        db_manager.add_user_game(self.user1_id, self.game1.id, "PC")
        db_manager.add_user_game(self.user2_id, self.game1.id, "PC")
        db_manager.add_user_game(self.user3_id, self.game1.id, "PC")

        db_manager.add_user_game(self.user1_id, self.game2.id, "PC")
        db_manager.add_user_game(self.user2_id, self.game2.id, "PC")
        db_manager.add_user_game(self.user3_id, self.game2.id, "PC")

        db_manager.add_user_game(self.user1_id, self.game3.id, "PC")

        db_manager.add_user_game(self.user2_id, self.game4.id, "PC")
        db_manager.add_user_game(self.user3_id, self.game4.id, "PC")

    def tearDown(self):
        """Close the database connection and remove the temporary database file."""
        db.close()
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_suggest_games_no_users(self):
        """Test that no suggestions are returned when the user list is empty."""
        suggestions = game_suggester.suggest_games([])
        self.assertEqual(suggestions, [])

    def test_suggest_games_all_users_common_game(self):
        """Test suggesting games when all users have a common game."""
        suggestions = game_suggester.suggest_games([self.user1_id, self.user2_id, self.user3_id])
        self.assertIn(self.game1, suggestions)
        self.assertEqual(len(suggestions), 2)

    def test_suggest_games_group_size_match(self):
        """Test that suggestions are filtered by group size."""
        suggestions = game_suggester.suggest_games([self.user1_id, self.user2_id], group_size=3)
        self.assertIn(self.game1, suggestions)  # Min 2, Max 4
        self.assertIn(self.game2, suggestions)  # Min 3, Max 5

    def test_suggest_games_last_played_scoring(self):
        """Test that games played less recently are scored higher."""
        # Mark Game A as played recently, Game B as played long ago
        Game.update(last_played=(datetime.now() - timedelta(days=1))).where(Game.id == self.game1.id).execute()
        Game.update(last_played=(datetime.now() - timedelta(days=10))).where(Game.id == self.game2.id).execute()

        suggestions = game_suggester.suggest_games([self.user1_id, self.user2_id])
        # Game B should be suggested before Game A due to older last_played date
        self.assertLess(suggestions.index(self.game2), suggestions.index(self.game1))

    def test_suggest_games_preferred_tags(self):
        """Test that suggestions can be filtered by preferred tags."""
        suggestions = game_suggester.suggest_games(
            [self.user1_id, self.user2_id, self.user3_id], preferred_tags=["strategy"]
        )
        self.assertIn(self.game1, suggestions)  # Game A has 'strategy'
        self.assertIn(self.game2, suggestions)  # Game B is still suggested but should be lower ranked
        self.assertLess(suggestions.index(self.game1), suggestions.index(self.game2))

    def test_suggest_games_liked_disliked_scoring(self):
        """Test that liked games are boosted and disliked games are penalized."""
        # User1 likes Game B, dislikes Game A
        db_manager.set_game_liked_status(self.user1_id, self.game2.id, True)
        db_manager.set_game_disliked_status(self.user1_id, self.game1.id, True)

        suggestions = game_suggester.suggest_games([self.user1_id, self.user2_id])
        # Game B should be ranked higher than Game A due to like/dislike
        self.assertLess(suggestions.index(self.game2), suggestions.index(self.game1))

    def test_suggest_games_recently_won_penalty(self):
        """Test that recently won games are penalized."""
        # Create a recent game night where Game A was selected
        recent_time = datetime.now() - timedelta(days=5)
        game_night_id = db_manager.add_game_night_event(self.user1_id, recent_time, "channel_id")
        db_manager.update_game_night_selected_game(game_night_id, self.game1.id)

        suggestions = game_suggester.suggest_games([self.user1_id, self.user2_id, self.user3_id])
        # Game A should be penalized and ranked lower
        if self.game1 in suggestions and self.game2 in suggestions:
            self.assertGreater(suggestions.index(self.game1), suggestions.index(self.game2))


if __name__ == '__main__':
    unittest.main()
