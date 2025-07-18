import io
import os
import sys
from urllib.parse import unquote

# Add the project root to the Python path BEFORE trying to import from it.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont

from data import db_manager
from steam.steam_api import get_game_details as fetch_steam_details
from utils.logging import logger

app = Flask(__name__)

# --- Page Rendering Routes ---
@app.route('/')
def index():
    """Render the landing page for the web companion."""
    return (
        '<body style="background-color: #2c2f33; color: #fff; font-family: sans-serif; '
        'text-align: center; padding-top: 5em;">'
        '<h1>Game Night Bot Companion</h1>'
        '<p>Use the <code>/view_library</code> command in Discord to see a library.</p>'
        '</body>'
    )


@app.route('/library/<discord_id>')
def show_library(discord_id):
    """Render the library view page for a specific user."""
    viewer_id = request.args.get('viewer_id')
    return render_template('index.html', discord_id=discord_id, viewer_id=viewer_id)

# --- Data API Routes ---
@app.route('/api/users')
def get_all_users_api():
    """Provide a list of all registered users."""
    users = db_manager.get_all_users()
    user_list = [{"discord_id": u.discord_id, "username": u.username} for u in users]
    return jsonify(user_list)

@app.route('/api/games/<discord_id>')
def get_user_games(discord_id):
    """Fetch all games owned by a specific user."""
    logger.info(f"Attempting to fetch games for Discord ID: {discord_id}")
    user_db = db_manager.get_user_by_discord_id(discord_id)
    if not user_db:
        logger.warning(f"User with Discord ID {discord_id} not found in database.")
        return jsonify({"error": "User not found"}), 404
    logger.info(f"Found user: {user_db.username} (DB ID: {user_db.id})")
    user_games_data = db_manager.get_user_game_ownerships(user_db.id)
    logger.info(f"Retrieved {len(user_games_data)} game ownership records for user {user_db.username}.")
    # Consolidate games by IGDB ID to handle multiple sources
    consolidated_games = {}
    for ug in user_games_data:
        game_id = ug.game.igdb_id
        if game_id not in consolidated_games:
            consolidated_games[game_id] = {
                "id": ug.game.igdb_id,
                "name": ug.game.title,
                "steam_appid": ug.game.steam_appid,
                "sources": [], # This will store all sources for this game
                "tags": ug.game.tags or "",
                "min_players": ug.game.min_players,
                "max_players": ug.game.max_players,
                "liked": ug.liked,
                "disliked": ug.disliked,
                "is_installed": ug.is_installed, # Take installed status from the first encountered ownership
                "cover_url": ug.game.cover_url,
                "description": ug.game.description,
                "metacritic": ug.game.metacritic,
                "multiplayer_info": ug.game.multiplayer_info,
                "release_date": ug.game.release_date,
                "is_game_pass": False # Initialize as False, set to True if a 'game_pass' source is found
            }
        # Check if this specific UserGame entry is from Game Pass
        if ug.source == "game_pass":
            consolidated_games[game_id]["is_game_pass"] = True
        consolidated_games[game_id]["sources"].append(ug.source)

    games_list = list(consolidated_games.values())
    return jsonify(games_list)

@app.route('/api/game_details/<int:game_id>')
async def get_game_details_api(game_id):
    """
    Fetch detailed information for a single game, updating from Steam if needed.

    This also finds out who owns the game.
    """
    game = db_manager.get_game_details(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    if (not game.description or not game.release_date or not game.metacritic) and game.steam_appid:
        # This logic is now handled by db_manager.add_game when the game is initially added or updated.
        # We should just rely on the data already in the Game model.
        pass

    # Get the list of owners directly with usernames from our updated function
    owners_info = db_manager.get_game_owners_with_platforms(game.id)

    # === THIS IS THE FIX ===
    # We can now build the list much more simply because owners_info contains usernames
    # The loop now expects three items: oid, uname, p
    owner_list = [{"username": uname, "platform": p} for oid, uname, p in owners_info]

    details = {
        "name": game.name,
        "steam_appid": game.steam_appid,
        "description": game.description,
        "metacritic": game.metacritic or "Not available",
        "multiplayer_info": game.multiplayer_info,
        "owners": owner_list
    }
    return jsonify(details)

# --- Game Management API Routes ---


@app.route('/api/manage/toggle_owned', methods=['POST'])
def toggle_owned_api():
    """API endpoint to toggle the 'owned' status of a user's game."""
    data = request.json
    user_db = db_manager.get_user_by_discord_id(data.get('discord_id'))
    if not user_db:
        return jsonify({"error": "User not found"}), 404

    game_id = data.get('game_id')
    ownership = db_manager.get_user_game_ownership(user_db.id, game_id)

    if ownership:
        db_manager.remove_user_game(user_db.id, game_id)
        return jsonify({"success": True, "owned": False})
    else:
        # NOTE: When adding a game back, we don't know the original platform.
        # Defaulting to 'PC'. This is a limitation of the current design.
        db_manager.add_user_game(user_db.id, game_id, "PC")
        return jsonify({"success": True, "owned": True})

@app.route('/api/manage/toggle_installed', methods=['POST'])
def toggle_installed_api():
    """API endpoint to toggle the 'installed' status of a user's game."""
    data = request.json
    user_db = db_manager.get_user_by_discord_id(data.get('discord_id'))
    if not user_db:
        return jsonify({"error": "User not found"}), 404
    ownership = db_manager.get_user_game_ownership(user_db.id, data.get('game_id'))
    if ownership:
        new_status = not ownership.is_installed
        db_manager.set_user_game_installed(user_db.id, data.get('game_id'), new_status)
        return jsonify({"success": True, "is_installed": new_status})
    return jsonify({"error": "Ownership record not found"}), 404

@app.route('/api/manage/like_game', methods=['POST'])
def like_game_api():
    """API endpoint to like a game for a user."""
    data = request.json
    user_db = db_manager.get_user_by_discord_id(data.get('discord_id'))
    if not user_db:
        return jsonify({"error": "User not found"}), 404

    ownership = db_manager.get_user_game_ownership(user_db.id, data.get('game_id'))
    if not ownership:
        return jsonify({"error": "Ownership record not found"}), 404

    new_liked_status = not ownership.liked # Toggle logic
    db_manager.set_user_game_like_dislike_status(user_db.id, data.get('game_id'), new_liked_status, False)
    return jsonify({"success": True, "liked": new_liked_status, "disliked": False})

@app.route('/api/manage/dislike_game', methods=['POST'])
def dislike_game_api():
    """API endpoint to dislike a game for a user."""
    data = request.json
    user_db = db_manager.get_user_by_discord_id(data.get('discord_id'))
    if not user_db:
        return jsonify({"error": "User not found"}), 404

    ownership = db_manager.get_user_game_ownership(user_db.id, data.get('game_id'))
    if not ownership:
        return jsonify({"error": "Ownership record not found"}), 404

    new_disliked_status = not ownership.disliked # Toggle logic
    db_manager.set_user_game_like_dislike_status(user_db.id, data.get('game_id'), False, new_disliked_status)
    return jsonify({"success": True, "liked": False, "disliked": new_disliked_status})

# --- Image Generator Route ---
@app.route('/api/placeholder/<path:text>')
def generate_placeholder(text):
    """Generate a placeholder image with the given text."""
    game_title = unquote(text)
    width, height = 460, 215
    background_color = (50, 50, 50)
    img = Image.new('RGB', (width, height), color=background_color)
    draw = ImageDraw.Draw(img)
    try:
        font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'Oswald-Regular.ttf')
        font = ImageFont.truetype(font_path, 30)
    except IOError:
        font = ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), game_title, font=font)
    text_x = (width - (text_bbox[2] - text_bbox[0])) / 2
    text_y = (height - (text_bbox[3] - text_bbox[1])) / 2
    draw.text((text_x, text_y), game_title, font=font, fill=(255, 255, 255))
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
