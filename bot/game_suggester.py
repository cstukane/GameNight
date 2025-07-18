import os
import sys
from datetime import datetime, timedelta

# Add the project root to the Python path before any other imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import db_manager
from data.models import GameExclusion, GameNight, UserAvailability, UserGame


def suggest_games(available_user_ids, group_size=None, preferred_tags=None):
    """Suggests games based on common ownership among available users, group size, and time since last played.

    Args:
    ----
        available_user_ids (list): A list of database user IDs who are available for the game night.
        group_size (int, optional): The number of players in the group. Defaults to None.
        preferred_tags (list, optional): A list of preferred tags. Defaults to None.

    Returns:
    -------
        list: A list of suggested game names, ordered by score.

    """
    today_weekday = datetime.now().weekday() # Monday is 0 and Sunday is 6

    # Filter out users who are busy today
    truly_available_user_ids = []
    for user_id in available_user_ids:
        try:
            availability = UserAvailability.get(user=user_id)
            if availability.available_days:
                available_days = [int(d) for d in availability.available_days.split(',')]
                if today_weekday in available_days:
                    truly_available_user_ids.append(user_id)
            # If available_days is empty, the user is not available for specific days.
            # Do nothing, so they are not added to truly_available_user_ids.
        except UserAvailability.DoesNotExist:
            truly_available_user_ids.append(user_id) # Assume available if no record exists

    if not truly_available_user_ids:
        return []

    common_games_data = db_manager.get_games_owned_by_users(truly_available_user_ids)
    print(f"Common games data: {common_games_data}")

    if not common_games_data:
        return []
    # Filter out excluded games for each user
    filtered_games = []
    for game in common_games_data:
        is_excluded_for_any_user = False
        for user_id in available_user_ids:
            if GameExclusion.get_or_none(user=user_id, game=game.igdb_id):
                is_excluded_for_any_user = True
                break
        if not is_excluded_for_any_user:
            filtered_games.append(game)
    print(f"Filtered games: {filtered_games}")

    scored_games = []
    for game in filtered_games:
        score = 0

        # Score based on group size match
        if group_size is not None:
            if game.min_players is not None and game.max_players is not None:
                if game.min_players <= group_size <= game.max_players:
                    score += 10 # Good match
                elif game.min_players <= group_size + 2 and game.max_players >= group_size - 2: # A bit flexible
                    score += 5
            elif game.min_players is not None and group_size >= game.min_players:
                score += 3 # Only min players specified, but fits
            elif game.max_players is not None and group_size <= game.max_players:
                score += 3 # Only max players specified, but fits

        # Score based on time since last played (prioritize older plays)
        if game.last_played:
            time_diff = datetime.now() - game.last_played
            # Penalize recently played games more heavily
            # Example: -10 points if played today, -5 if played within a week, etc.
            if time_diff.days < 1:
                score -= 10
            elif time_diff.days < 7:
                score -= 5
            # Reward games played longer ago (e.g., +1 point per month since last played, up to a cap)
            score += min(time_diff.days // 30, 10) # Max 10 points for age

        # Score based on preferred tags
        if preferred_tags and game.tags:
            game_tags = game.tags.split(',')
            for tag in preferred_tags:
                if tag in game_tags:
                    score += 50

        # Score based on liked/disliked status
        for user_id in available_user_ids:
            user_game_entry = UserGame.get_or_none(user=user_id, game=game.igdb_id)
            if user_game_entry:
                if user_game_entry.liked:
                    score += 20 # Strong boost for liked games
                elif user_game_entry.disliked:
                    score -= 20 # Strong penalty for disliked games

                if user_game_entry.is_installed:
                    score += 15 # Significant boost for installed games

        # Penalize games that have won recently
        recent_game_nights = GameNight.select().where(GameNight.scheduled_time > datetime.now() - timedelta(days=30))
        for gn in recent_game_nights:
            if gn.selected_game and gn.selected_game.igdb_id == game.igdb_id:
                score -= 50 # Heavy penalty for recently won games

        scored_games.append((game, score))

    # Sort games by score in descending order
    scored_games.sort(key=lambda x: x[1], reverse=True)

    return [game_obj for game_obj, score in scored_games]
