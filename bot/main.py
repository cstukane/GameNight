import asyncio
import os
import sys
from asyncio import subprocess

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import httpx
from xbox.webapi.authentication.manager import SignedSession
from data import db_manager


import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands

# from bot.game_pass_fetcher import fetch_game_pass_games  # Assuming this function exists
from data.database import initialize_database
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
        self.web_client = None # Initialize web_client
        self.logger = logger # Assign the main logger to the bot instance

    async def setup_hook(self):
        """Perform asynchronous setup after the bot is ready but before it has connected."""
        # Initialize aiohttp ClientSession
        # Create a persistent client session for the bot to use for all web requests.
        # The xbox-webapi requires a SignedSession.
        from xbox.webapi.common.signed_session import SignedSession
        self.web_client = SignedSession(httpx.AsyncClient())

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

    async def on_disconnect(self):
        """Event that runs when the bot disconnects from Discord."""
        if self.web_client:
            await self.web_client.aclose()
            logger.info("httpx ClientSession closed.")

    async def on_ready(self):
        """Event that runs when the bot has successfully connected to Discord."""
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Commands synced to guild {MY_GUILD.id}')
        logger.info('------')

        # Schedule recurring tasks

        #         self.scheduler.add_job(
#             fetch_game_pass_games, 'interval',
#             weeks=4, next_run_time=datetime.now()
#         )

        # Schedule weekly availability poll on Mondays at a specific time (e.g., 9 AM)
        self.scheduler.add_job(
            self.get_cog('AutomationTasks').start_weekly_availability_poll, 'cron',
            day_of_week='mon', hour=9, minute=0, args=[]
        )


from utils.ngrok import get_public_url


async def main():
    """Run the main entry point for the bot."""
    # Start ngrok and get the public URL
    public_url = get_public_url(port=5001)
    if public_url:
        os.environ['BASE_URL'] = public_url
        logger.info(f"BASE_URL set to: {public_url}")
    else:
        logger.critical("Could not get ngrok URL. Web library will be unavailable.")
        # Depending on desired behavior, you might want to exit or just continue without web features.
        # For now, we'll just log the error and continue.

    if not DISCORD_BOT_TOKEN:
        logger.error("Error: DISCORD_BOT_TOKEN not found. Please set it in your .env file.")
        return

    # Initialize the database
    initialize_database()

    # Check if Game Pass catalog is empty and populate if necessary
    game_pass_catalog = db_manager.get_game_pass_catalog()
    if not game_pass_catalog:
        logger.info("Game Pass catalog is empty. Populating it now...")
        # --- CHANGE IS HERE ---
        # We set the 'cwd' (current working directory) to 'gamepass_api'
        # so the Node.js script runs from the correct folder.
        process = await asyncio.create_subprocess_shell(
            "node index.js",
            cwd="gamepass_api",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info("Game Pass catalog populated successfully.")
            if stdout:
                logger.info(f"Node script output:\n{stdout.decode().strip()}")
        else:
            logger.error(f"Error populating Game Pass catalog: {stderr.decode().strip()}")
    else:
        logger.info("Game Pass catalog already populated.")

    intents = discord.Intents.default()
    intents.voice_states = True
    bot = GameNightBot(intents=intents)
    await bot.start(DISCORD_BOT_TOKEN)

    # Start the daily Game Pass sync task after the bot is ready and catalog is populated
    if bot.get_cog('AutomationTasks'):
        logger.info("Attempting to start daily Game Pass sync task...")
        bot.get_cog('AutomationTasks').daily_game_pass_sync.start()


if __name__ == "__main__":
    asyncio.run(main())
