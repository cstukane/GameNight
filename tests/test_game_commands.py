from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio  # New import
from discord.ext import commands

from bot.cogs.game_commands import GameCommands
from data.database import initialize_database  # New import
from data.models import Game, User, UserGame, db


@pytest_asyncio.fixture
async def mock_bot():
    """Mock the Discord bot for testing."""
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, application_id=1234567890) # Mock application ID
    cog = GameCommands(bot)
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
    db.drop_tables([User, Game, UserGame])
    db.close()


