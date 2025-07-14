import os

from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.getenv("STEAM_API_KEY", "") # Default to empty string if not set
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "") # Default to empty string if not set
STEAMGRIDDB_API_KEY = os.getenv("STEAMGRIDDB_API_KEY", "") # Default to empty string if not set
DATABASE_FILE = os.getenv("DATABASE_FILE", "data/users.db")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
