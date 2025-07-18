# utils/config.py

import os

from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.getenv("STEAM_API_KEY", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
STEAMGRIDDB_API_KEY = os.getenv("STEAMGRIDDB_API_KEY", "")

# --- ADD THESE TWO LINES ---
IGDB_CLIENT_ID = os.getenv("IGDB_CLIENT_ID", "")
IGDB_CLIENT_SECRET = os.getenv("IGDB_CLIENT_SECRET", "")
XBOX_CLIENT_ID = os.getenv("XBOX_CLIENT_ID", "")
XBOX_CLIENT_SECRET = os.getenv("XBOX_CLIENT_SECRET", "")
XBOX_REDIRECT_URI = os.getenv("XBOX_REDIRECT_URI", "")
# -------------------------

DATABASE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "users.db"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
