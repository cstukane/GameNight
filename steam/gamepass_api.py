from data.models import GamePassGame, db
from utils.logging import logger


def fetch_game_pass_games():
    """Fetch the list of Game Pass games from an online source and store them."""
    # Placeholder for actual fetching logic.
    # This would involve making an HTTP request to a community-maintained API or
    # scraping a reliable source. For now, we'll simulate some data.
    game_pass_list = [
        "Minecraft",
        "Forza Horizon 5",
        "Halo Infinite",
        "Gears 5",
        "Sea of Thieves",
        "Starfield"  # Example game
    ]

    try:
        with db.atomic():
            for game_name in game_pass_list:
                GamePassGame.get_or_create(name=game_name)
        logger.info("Successfully updated Game Pass game list.")
    except Exception as e:
        logger.error(f"Error updating Game Pass game list: {e}")


if __name__ == "__main__":
    # This block can be used for testing the function independently
    from data.database import initialize_database
    initialize_database()
    fetch_game_pass_games()
