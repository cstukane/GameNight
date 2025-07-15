import os
import re
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from bot.game_suggester import suggest_games
from data import db_manager
from data.models import Game
from steam.steam_api import get_game_details
from steam.steamgriddb_api import get_game_image
from utils.errors import GameNightError, GameNotFoundError, UserNotFoundError
from utils.logging import logger

ALLOWED_PLATFORMS = ["PC", "Xbox", "PlayStation", "Switch"]


class GameSuggestionView(discord.ui.View):
    """A view for displaying game suggestions with interactive buttons."""

    # This class remains as it is a core part of the game night workflow.
    def __init__(self, suggested_games):
        super().__init__(timeout=180)
        self.suggested_games = suggested_games
        self.add_item(discord.ui.Button(label="Create Poll", style=discord.ButtonStyle.green, custom_id="create_poll"))
        for game in suggested_games[:3]:
            if game.steam_appid:
                button = discord.ui.Button(
                    label=f"Launch {game.name}",
                    style=discord.ButtonStyle.blurple,
                    custom_id=f"launch_game_{game.id}"
                )
                self.add_item(button)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        """Handle errors in the view."""
        logger.error(f"Error in GameSuggestionView: {error}")
        traceback.print_exc()
        message = "An error occurred."
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check for and handle interactions with the view's components."""
        custom_id = interaction.data["custom_id"]
        if custom_id == "create_poll":
            await interaction.response.send_message("Poll creation logic will go here!", ephemeral=True)
            return False
        elif custom_id.startswith("launch_game_"):
            await interaction.response.defer(ephemeral=True)
            user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
            game_id = int(custom_id.replace("launch_game_", ""))
            game = Game.get_by_id(game_id)
            if not user_db:
                await interaction.followup.send("You are not registered. Please add a game first.", ephemeral=True)
                return False
            user_game_ownership = db_manager.get_user_game_ownership(user_db.id, game.id)
            if user_game_ownership and game:
                if user_game_ownership.platform == "PC" and game.steam_appid:
                    message = f"Click here to launch **{game.name}**: <steam://run/{game.steam_appid}>"
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    message = (
                        f"You own **{game.name}** on {user_game_ownership.platform}. "
                        "Please launch it from the app or console."
                    )
                    await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.followup.send(f"You don't have **{game.name}** in your library.", ephemeral=True)
            return False
        return True


class GameCommands(commands.Cog):
    """A cog for game-related commands like adding, managing, and suggesting games."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle application command errors for this cog."""
        msg = "An unexpected error occurred. Please try again later."
        if isinstance(error, (GameNightError, GameNotFoundError, UserNotFoundError)):
            msg = str(error)
        else:
            logger.error(f"An unexpected error occurred in GameCommands: {error}")
            traceback.print_exc()
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="view_library", description="Generates a link to your interactive web library.")
    @app_commands.describe(user="The user whose library you want to view. Defaults to yourself.")
    async def view_library(self, interaction: discord.Interaction, user: discord.Member = None):
        """Generate a link to the user's web-based game library."""
        await interaction.response.defer()

        target_user = user or interaction.user

        user_db = db_manager.get_user_by_discord_id(str(target_user.id))
        if not user_db:
            error_msg = f"{target_user.display_name} does not have a profile yet. Use `/add_game` or `/set_steam_id`."
            raise UserNotFoundError(error_msg)

        base_url = os.getenv("BASE_URL")
        if not base_url:
            error_msg = "Error: The web library URL is not configured by the bot owner."
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        library_url = f"{base_url}/library/{target_user.id}"

        embed_desc = (
            f"Click the button below to browse **{target_user.display_name}s** "
            "complete and filterable game library in your web browser!"
        )
        embed = discord.Embed(
            title=f"{target_user.display_name}'s Game Library",
            description=embed_desc,
            color=target_user.color
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Open Web Library", style=discord.ButtonStyle.link, url=library_url))

        await interaction.followup.send(embed=embed, view=view)

    # ... other commands like manage_games, suggest_games, add_game ...
    # NOTE: The 'view_games' command has been removed as this functionality is
    # now better served by the filterable web interface.

    @app_commands.command(name="manage_games", description="Manage your game library.")
    async def manage_games(self, interaction: discord.Interaction):
        """Provide an interactive view to manage a user's game library."""
        await interaction.response.defer(ephemeral=True)
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        if not user_db:
            raise UserNotFoundError("You have not added any games yet.")

        user_games_data = db_manager.get_user_game_ownerships(user_db.id)
        if not user_games_data:
            raise GameNotFoundError("You have no games in your library.")

        games = sorted([ug.game for ug in user_games_data], key=lambda g: g.name.lower())

        view = GameManagementView(games, user_db.id, interaction.user.id)
        embed = await view.create_embed()

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="suggest_games", description="Suggests games for the group.")
    @app_commands.describe(
        group_size="The number of players in your group.",
        preferred_tags="A comma-separated list of preferred tags.",
        users="Mention specific users to include (e.g., @user1 @user2)."
    )
    async def suggest(
        self, interaction: discord.Interaction, group_size: int = None, preferred_tags: str = None, users: str = None
    ):
        """Suggest games based on common ownership and preferences."""
        await interaction.response.defer()
        available_user_ids = []
        if users:
            user_mentions = re.findall(r'<@!?(\d+)>', users)
            for user_id_str in user_mentions:
                user_db = db_manager.get_user_by_discord_id(user_id_str)
                if user_db:
                    available_user_ids.append(user_db.id)
            if not available_user_ids:
                raise UserNotFoundError("None of the specified users are registered.")
        else:
            all_users = db_manager.get_all_users()
            if not all_users:
                raise UserNotFoundError("No users found.")
            available_user_ids = [user.id for user in all_users]

        if preferred_tags:
            tags = preferred_tags.split(',')
        else:
            tags = None
        suggested_games = suggest_games(available_user_ids, group_size=group_size, preferred_tags=tags)
        if not suggested_games:
            raise GameNotFoundError("I couldn't find any suitable games for your group.")

        embed = discord.Embed(title="Tonight's Game Suggestions", color=discord.Color.purple())
        for game in suggested_games[:3]:
            value = f"Players: {game.min_players or '?'} | Tags: {game.tags or 'N/A'}"
            embed.add_field(name=game.name, value=value, inline=False)
        if suggested_games:
            first_game_image = get_game_image(suggested_games[0].name, "grid")
            if first_game_image:
                embed.set_thumbnail(url=first_game_image)
        view = GameSuggestionView(suggested_games)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="add_game", description="Manually adds a game you own to your library.")
    @app_commands.describe(
        name="The name of the game.",
        platform="The platform you own the game on.",
        steam_appid="The Steam App ID of the game (if applicable).",
        min_players="Minimum number of players.",
        max_players="Maximum number of players."
    )
    async def add_game(
        self, interaction: discord.Interaction, name: str, platform: str,
        steam_appid: int = None, min_players: int = None, max_players: int = None
    ):
        """Manually add a game to your library."""
        await interaction.response.defer(ephemeral=True)
        if platform not in ALLOWED_PLATFORMS:
            error_msg = f"Invalid platform. Choose from: {', '.join(ALLOWED_PLATFORMS)}"
            raise GameNightError(error_msg)
        if steam_appid:
            details = get_game_details(steam_appid)
        else:
            details = {}
        game_name = details.get('name', name)
        tags = ",".join([g['description'] for g in details.get('genres', [])])
        release_date = details.get('release_date', {}).get('date')
        description = details.get('short_description')
        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        game_db_id = db_manager.add_game(game_name, steam_appid, tags, min_players, max_players, release_date, description)
        db_manager.add_user_game(user_db_id, game_db_id, platform)
        success_msg = f"Successfully added **{game_name}** on **{platform}** to your library!"
        await interaction.followup.send(success_msg)

    @add_game.autocomplete('name')
    async def game_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for game names."""
        return [app_commands.Choice(name=g, value=g) for g in db_manager.search_games_by_name(current)][:25]

    @add_game.autocomplete('platform')
    async def platform_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for platform names."""
        return [app_commands.Choice(name=p, value=p) for p in ALLOWED_PLATFORMS if current.lower() in p.lower()]


async def setup(bot):
    """Load the GameCommands cog."""
    await bot.add_cog(GameCommands(bot))


class GameManagementView(discord.ui.View):
    """A view to manage games in a user's library."""

    # This class remains as it is a Discord-native management tool.
    def __init__(self, games, user_id, original_interactor_id):
        super().__init__(timeout=300)
        self.games = games
        self.user_id = user_id
        self.original_interactor_id = original_interactor_id
        self.build_view()

    def build_view(self):
        """Clear and rebuild the view components."""
        self.clear_items()
        for i, game in enumerate(self.games):
            user_game = db_manager.get_user_game_ownership(self.user_id, game.id)
            owned = user_game is not None
            installed = user_game.is_installed if owned else False
            current_row = i // 2
            owned_label = f"{game.name} - Owned"
            owned_style = discord.ButtonStyle.success if owned else discord.ButtonStyle.secondary
            owned_button = discord.ui.Button(
                label=owned_label[:80], custom_id=f"toggle_owned_{game.id}",
                style=owned_style, row=current_row
            )
            self.add_item(owned_button)
            installed_label = "Installed" if installed else "Not Installed"
            installed_style = discord.ButtonStyle.blurple if installed else discord.ButtonStyle.grey
            installed_button = discord.ui.Button(
                label=installed_label, custom_id=f"toggle_installed_{game.id}",
                style=installed_style, disabled=not owned, row=current_row
            )
            self.add_item(installed_button)

    async def create_embed(self) -> discord.Embed:
        """Create the embed for the game management view."""
        embed_desc = "Toggle ownership or installed status. This message is only visible to you."
        embed = discord.Embed(title="Manage Your Games", description=embed_desc, color=discord.Color.dark_grey())
        if not self.games:
            embed.description += "\n\nYou have no games to manage."
        else:
            field_text = []
            for game in self.games:
                user_game = db_manager.get_user_game_ownership(self.user_id, game.id)
                owned_emoji = '✅' if user_game else '❌'
                installed_emoji = '✅' if user_game and user_game.is_installed else '❌'
                field_text.append(f"**{game.name}** (Owned: {owned_emoji} | Installed: {installed_emoji})")
            embed.add_field(name="Your Library", value="\n".join(field_text), inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interactor is the original user."""
        if interaction.user.id != self.original_interactor_id:
            await interaction.response.send_message("You can't manage someone else's library!", ephemeral=True)
            return False
        await self.handle_interaction(interaction)
        return False

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        """Handle errors in the view."""
        logger.error(f"Error in GameManagementView: {error}")
        traceback.print_exc()
        message = "An error occurred."
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)

    async def handle_interaction(self, interaction: discord.Interaction):
        """Handle button presses for managing games."""
        await interaction.response.defer(ephemeral=True)
        custom_id = interaction.data["custom_id"]
        try:
            action, sub_action, game_id_str = custom_id.split("_", 2)
            game_id = int(game_id_str)
        except ValueError:
            return
        if action == "toggle":
            user_game = db_manager.get_user_game_ownership(self.user_id, game_id)
            if sub_action == "owned":
                if user_game:
                    db_manager.remove_user_game(self.user_id, game_id)
                else:
                    db_manager.add_user_game(self.user_id, game_id, "PC")
            elif sub_action == "installed":
                if user_game:
                    db_manager.set_user_game_installed(self.user_id, game_id, not user_game.is_installed)
        self.build_view()
        new_embed = await self.create_embed()
        await interaction.edit_original_response(embed=new_embed, view=self)
