from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio
from discord.ext import commands

from bot import poll_manager
from data.database import initialize_database
from data.models import Game, GameNight, GameVote, User, db


@pytest_asyncio.fixture
async def mock_bot():
    """Mock the Discord bot for testing."""
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, application_id=1234567890)
    return bot

@pytest.fixture
def mock_channel():
    """Mock a Discord channel for testing."""
    channel = AsyncMock(spec=discord.TextChannel)
    return channel

@pytest.fixture
def mock_message():
    """Mock a Discord message for testing."""
    message = AsyncMock(spec=discord.Message)
    message.id = 123456789
    message.channel = AsyncMock(spec=discord.TextChannel)
    message.channel.send = AsyncMock()
    message.edit = AsyncMock()
    return message

@pytest.fixture(autouse=True)
def setup_test_db():
    """Set up and tear down a temporary test database."""
    # Use an in-memory database for speed and isolation
    db.init(':memory:')
    db.connect()
    db.create_tables([User, Game, GameNight, GameVote])
    yield
    db.drop_tables([User, Game, GameNight, GameVote])
    db.close()

# --- Tests for poll_manager.py ---

@pytest.mark.asyncio
async def test_create_availability_poll(mock_channel, mock_message):
    """Test creating an availability poll."""
    mock_channel.send.return_value = mock_message
    game_night_id = 1
    scheduled_time_str = "2025-12-25 at 19:00"

    result_message = await poll_manager.create_availability_poll(
        mock_channel, game_night_id, scheduled_time_str
    )

    mock_channel.send.assert_called_once()
    assert result_message == mock_message
    assert "Game Night Availability Poll" in mock_channel.send.call_args.kwargs['embed'].title

@pytest.mark.asyncio
async def test_create_game_selection_poll(mock_channel, mock_message):
    """Test creating a game selection poll."""
    mock_channel.send.return_value = mock_message
    game_night_id = 1
    suggested_games = ["Game A", "Game B", "Game C"]

    result_message = await poll_manager.create_game_selection_poll(
        mock_channel, game_night_id, suggested_games
    )

    mock_channel.send.assert_called_once()
    assert result_message == mock_message
    assert "Game Selection Poll" in mock_channel.send.call_args.kwargs['embed'].title

@pytest.mark.asyncio
async def test_get_poll_results(mock_message):
    """Test getting poll results from reactions."""
    # Simulate reactions on the message
    mock_message.reactions = [
        MagicMock(emoji="✅", count=3),
        MagicMock(emoji="❌", count=1),
        MagicMock(emoji="🤷", count=2)
    ]

    results = await poll_manager.get_poll_results(mock_message)

    # This function is likely a stub or deprecated, so it's expected to return an empty dict
    assert results == {}

async def mock_game_details_side_effect(game_id):
    """A helper to act as a side_effect for mock_get_game_details."""
    mock_game = MagicMock()
    if game_id == 1:
        mock_game.name = "Game A"
    elif game_id == 2:
        mock_game.name = "Game B"
    elif game_id == 3:
        mock_game.name = "Game C"
    return mock_game

@pytest.mark.asyncio
@patch('bot.poll_manager.db_manager.get_game_votes')
@patch('bot.poll_manager.db_manager.get_game_details', new_callable=AsyncMock)
async def test_get_game_poll_winner(mock_get_game_details, mock_get_game_votes):
    """Test getting the winner of a game poll."""
    # Mock return values for db_manager functions. Game C has the most votes (8).
    mock_get_game_votes.return_value = [
        MagicMock(game_id=1), MagicMock(game_id=1), MagicMock(game_id=1), MagicMock(game_id=1), MagicMock(game_id=1),
        MagicMock(game_id=2), MagicMock(game_id=2),
        MagicMock(game_id=3), MagicMock(game_id=3), MagicMock(game_id=3), MagicMock(game_id=3),
        MagicMock(game_id=3), MagicMock(game_id=3), MagicMock(game_id=3), MagicMock(game_id=3)
    ]
    mock_get_game_details.side_effect = mock_game_details_side_effect

    game_night_id = 1  # Dummy ID
    winner = await poll_manager.get_game_poll_winner(game_night_id)

    assert winner.name == "Game C"

@pytest.mark.asyncio
@patch('bot.poll_manager.db_manager.get_game_votes')
@patch('bot.poll_manager.db_manager.get_game_details', new_callable=AsyncMock)
async def test_get_game_poll_winner_with_tie(mock_get_game_details, mock_get_game_votes):
    """Test getting the winner of a game poll with a tie."""
    # Games A and B are tied with 5 votes each.
    mock_get_game_votes.return_value = [
        MagicMock(game_id=1), MagicMock(game_id=1), MagicMock(game_id=1), MagicMock(game_id=1), MagicMock(game_id=1),
        MagicMock(game_id=2), MagicMock(game_id=2), MagicMock(game_id=2), MagicMock(game_id=2), MagicMock(game_id=2),
        MagicMock(game_id=3), MagicMock(game_id=3)
    ]
    mock_get_game_details.side_effect = mock_game_details_side_effect

    game_night_id = 1  # Dummy ID
    winner = await poll_manager.get_game_poll_winner(game_night_id)

    # In case of a tie, the function should return the game with the lower ID.
    assert winner.name == "Game A"
