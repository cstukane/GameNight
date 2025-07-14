# Game Night Discord Bot

This is a Discord bot designed to help organize game nights, manage game libraries, and facilitate game suggestions and polls.

## Features

- **Game Library Management:** Users can add games they own, link their Steam accounts to sync libraries, and view their own or others' game collections.
- **Game Suggestions:** The bot can suggest games based on group size and shared ownership.
- **Game Night Scheduling:** Schedule game nights, set availability, and finalize game choices through polls.
- **Voice Activity Tracking:** Tracks user voice chat activity.
- **Reminders:** Sends reminders for upcoming game nights.

## Setup and Installation

### Prerequisites

- Python 3.8+
- Discord Bot Token (from [Discord Developer Portal](https://discord.com/developers/applications))
- Steam Web API Key (optional, for Steam library syncing)
- SteamGridDB API Key (optional, for game cover art)

### Installation Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/game-night-bot.git
    cd game-night-bot
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: .\venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a `.env` file:**
    Create a file named `.env` in the root directory of the project and add your bot token and API keys:
    ```
    DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
    STEAM_API_KEY=YOUR_STEAM_API_KEY
    STEAMGRIDDB_API_KEY=YOUR_STEAMGRIDDB_API_KEY
    ```
    *Replace `YOUR_DISCORD_BOT_TOKEN`, `YOUR_STEAM_API_KEY`, and `YOUR_STEAMGRIDDB_API_KEY` with your actual keys.*

5.  **Run the bot:**
    ```bash
    python bot/main.py
    ```

    On Windows, you can use the provided `run_bot.bat` script:
    ```bash
    .\run_bot.bat
    ```

## Usage

Once the bot is running and added to your Discord server, you can use the following slash commands:

-   `/ping`: Check if the bot is responsive.
-   `/profile [user]`: View a user's profile and interactive game library.
-   `/set_steam_id <steam_id>`: Link your Steam account to auto-sync your library.
-   `/add_game <name> <platform> [steam_appid]`: Manually add a game to your library.
-   `/view_games`: See all games in the database in an interactive browser.
-   `/view_library [user]`: View your own or another user's game library browser.
-   `/suggest_games [group_size] [preferred_tags] [users]`: Get game suggestions for your group.
-   `/next_game_night <date> <time> [poll_close_time]`: Schedule a new game night and start a poll.
-   `/set_game_night_availability <id> <status>`: Set your availability for a game night.
-   `/set_weekly_availability`: Set your recurring available days for game nights.
-   `/finalize_game_night <id>`: (Organizer only) Finalize attendees and start the game poll.
-   `/set_reminder_offset <minutes>`: Set your preferred reminder time before a game night.
-   `/discord_wrapped [year]`: Shows your voice activity statistics.
-   `/game_night_history [user]`: Shows a user's past game night attendance.
-   `/set_planning_channel <channel>`: Sets the channel for game night planning polls.
-   `/set_main_channel <channel>`: Sets the main channel for polls and announcements.
-   `/configure_weekly_slots`: Configure the guild's weekly availability time slots for polls.

## Project Structure

-   `bot/`: Contains the main bot logic and cogs (command modules).
-   `data/`: Handles database interactions and models.
-   `steam/`: Contains modules for interacting with Steam and SteamGridDB APIs.
-   `utils/`: Utility functions, logging, and configuration.
-   `tests/`: Unit and integration tests.

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## License

This project is licensed under the MIT License.