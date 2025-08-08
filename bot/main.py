import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands

from data import db_manager

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
        self._did_fallback_sync = False  # Track whether we've done a fallback guild-only sync

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
                await self.load_extension(f'bot.cogs.{filename[:-3]}')
                logger.info(f"Loaded cog: {filename[:-3]}")

        # Add persistent views
        from bot.poll_manager import AvailabilityPollView
        self.add_view(AvailabilityPollView())

        # This syncs the command tree to the configured guild for fast availability.
        # Commands will appear instantly in this guild.
        try:
            self.tree.copy_global_to(guild=MY_GUILD)
            await self.tree.sync(guild=MY_GUILD)
            logger.info(f"Synced app commands to configured guild {MY_GUILD.id}")
        except Exception as e:
            logger.warning(f"Initial guild sync to {MY_GUILD.id} failed: {e}. Will try fallback on_ready sync.")

    async def on_disconnect(self):
        """Event that runs when the bot disconnects from Discord."""
        if self.web_client:
            await self.web_client.aclose()
            logger.info("httpx ClientSession closed.")

    async def on_ready(self):
        """Event that runs when the bot has successfully connected to Discord."""
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')

        # Fallback: fast guild-only sync to the first connected guild if needed
        # This ensures newly added commands (e.g., /import_gog) appear immediately during testing.
        try:
            if not self._did_fallback_sync:
                guilds = self.guilds
                if guilds:
                    fallback_guild = guilds[0]
                    # Copy global commands to the fallback guild and sync
                    self.tree.copy_global_to(guild=fallback_guild)
                    await self.tree.sync(guild=fallback_guild)
                    self._did_fallback_sync = True
                    logger.info(f"Fallback guild-only sync complete for guild {fallback_guild.id} ({fallback_guild.name}).")
                else:
                    logger.warning("No guilds found to perform fallback sync.")
        except Exception as e:
            logger.error(f"Fallback guild-only sync failed: {e}")

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

        # Install Node.js dependencies first
        logger.info("Installing Node.js dependencies for gamepass_api...")
        install_process = await asyncio.create_subprocess_shell(
            "npm install",
            cwd="gamepass_api",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        install_stdout, install_stderr = await install_process.communicate()

        if install_process.returncode == 0:
            logger.info("Node.js dependencies installed successfully.")
            if install_stdout:
                logger.info(f"npm install output:\n{install_stdout.decode().strip()}")
        else:
            logger.error(f"Error installing Node.js dependencies: {install_stderr.decode().strip()}")
            logger.error("Game Pass catalog population aborted due to dependency installation failure.")
            # Continue without populating Game Pass if dependencies fail
            # This might lead to further errors if the Node.js script relies on these.
            # Consider exiting or raising an exception here in a production environment.
            pass # Allow the bot to start even if this fails, but log the error

        # Run the Node.js script to populate the catalog
        logger.info("Running Node.js script to fetch Game Pass catalog...")
        process = await asyncio.create_subprocess_shell(
            "node ogindex.js",
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
    intents.members = True
    bot = GameNightBot(intents=intents)
    await bot.start(DISCORD_BOT_TOKEN)

    # Start the daily Game Pass sync task after the bot is ready and catalog is populated
    if bot.get_cog('AutomationTasks'):
        logger.info("Attempting to start daily Game Pass sync task...")
        bot.get_cog('AutomationTasks').daily_game_pass_sync.start()


if __name__ == "__main__":
    asyncio.run(main())
