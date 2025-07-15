import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands

# from bot.game_pass_fetcher import fetch_game_pass_games  # Assuming this function exists
from data.database import initialize_database
from steam.fetch_library import fetch_and_store_games_for_all_users
from utils.config import DISCORD_BOT_TOKEN
from utils.logging import logger

# Set up the guild (server) ID for immediate command syncing
MY_GUILD = discord.Object(id=1045175103249449000)

class GameNightBot(commands.Bot):
    """The main bot class for the Game Night Bot."""

    def __init__(self, *, intents: discord.Intents):
        """Initialize the GameNightBot."""
        super().__init__(command_prefix='', intents=intents)
        self.scheduler = AsyncIOScheduler()  # Initialize scheduler

    async def setup_hook(self):
        """Perform asynchronous setup after the bot is ready but before it has connected."""
        # Load cogs
        for filename in os.listdir('./bot/cogs'):
            if filename.endswith('.py'):
                if filename == 'automation_tasks.py': # Load automation_tasks last
                    continue
                await self.load_extension(f'bot.cogs.{filename[:-3]}')
                logger.info(f"Loaded cog: {filename[:-3]}")

        # Load automation_tasks last to ensure all other cogs are ready
        await self.load_extension('bot.cogs.automation_tasks')
        logger.info("Loaded cog: automation_tasks")

        # This syncs the command tree to the guild.
        # Commands will appear instantly in this guild.
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

    async def on_ready(self):
        """Event that runs when the bot has successfully connected to Discord."""
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Commands synced to guild {MY_GUILD.id}')
        logger.info('------')

        # Schedule recurring tasks
        self.scheduler.add_job(
            fetch_and_store_games_for_all_users, 'interval',
            weeks=1, next_run_time=datetime.now()
        )
        #         self.scheduler.add_job(
#             fetch_game_pass_games, 'interval',
#             weeks=4, next_run_time=datetime.now()
#         )

        # Schedule weekly availability poll on Mondays at a specific time (e.g., 9 AM)
        self.scheduler.add_job(
            self.get_cog('AutomationTasks').start_weekly_availability_poll, 'cron',
            day_of_week='mon', hour=9, minute=0, args=[]
        )


async def main():
    """Run the main entry point for the bot."""
    if not DISCORD_BOT_TOKEN:
        logger.error("Error: DISCORD_BOT_TOKEN not found. Please set it in your .env file.")
        return

    # Initialize the database
    initialize_database()

    intents = discord.Intents.default()
    intents.voice_states = True
    bot = GameNightBot(intents=intents)
    await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
