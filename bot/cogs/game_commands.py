import os
import re
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from bot.game_suggester import suggest_games
from data import db_manager
from steam.igdb_api import igdb_api
from utils.errors import GameNightError, GameNotFoundError, UserNotFoundError
from utils.logging import logger


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
                    label=f"Launch {game.title}",
                    style=discord.ButtonStyle.blurple,
                    custom_id=f"launch_game_{game.igdb_id}"
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
            igdb_id = int(custom_id.replace("launch_game_", ""))
            game = db_manager.get_game_by_igdb_id(igdb_id)
            if not user_db:
                await interaction.followup.send("You are not registered. Please add a game first.", ephemeral=True)
                return False
            user_game_ownership = db_manager.get_user_game_ownership(user_db.id, game.igdb_id)
            if user_game_ownership and game:
                if user_game_ownership.source == "Steam" and game.steam_appid:
                    message = f"Click here to launch **{game.title}**: <steam://run/{game.steam_appid}>"
                elif user_game_ownership.source == "Xbox":
                    message = f"You own **{game.title}** on Xbox. Please launch it from your Xbox console or the Xbox app on PC."
                elif user_game_ownership.source == "PlayStation":
                    message = f"You own **{game.title}** on PlayStation. Please launch it directly from your PlayStation console."
                elif user_game_ownership.source == "Switch":
                    message = f"You own **{game.title}** on Nintendo Switch. Please launch it directly from your Nintendo Switch console."
                elif user_game_ownership.source == "PC" or user_game_ownership.source == "manual":
                    message = f"You own **{game.title}** on PC. Please launch it from your desktop shortcut or game launcher."
                else:
                    message = (
                        f"You own **{game.title}** on {user_game_ownership.source}. "
                        "Please launch it from the app or console."
                    )
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.followup.send(f"You don't have **{game.title}** in your library.", ephemeral=True)
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

        library_url = f"{base_url}/library/{target_user.id}?viewer_id={interaction.user.id}"

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
            value = f"Players: {game.min_players or '?'} - {game.max_players or '?'}\n"
            if game.cover_url:
                value += f"[Cover Art]({game.cover_url})\n"
            embed.add_field(name=game.title, value=value, inline=False)
        if suggested_games and suggested_games[0].cover_url:
            embed.set_thumbnail(url=suggested_games[0].cover_url)
        view = GameSuggestionView(suggested_games)
        await interaction.followup.send(embed=embed, view=view)

    # @app_commands.command(name="add_game", description="Manually adds a game you own to your library.")
    # @app_commands.describe(name="The name of the game.", source="The platform you own the game on.")
    # async def add_game(self, interaction: discord.Interaction, name: int, source: str):
    #     """Manually add a game to your library."""
    #     await interaction.response.defer(ephemeral=True)
    #     igdb_id = name # The 'name' is now the IGDB ID from the autocomplete choice

    #     user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
    #     game_db_id = await db_manager.add_game(igdb_id=igdb_id)

    #     if not game_db_id:
    #         raise GameNotFoundError(f"Could not find or add game with IGDB ID: {igdb_id}")

    #     # Retrieve the game object to get the potentially updated title from IGDB
    #     game_obj = db_manager.get_game_by_igdb_id(game_db_id)
    #     game_title = game_obj.title if game_obj else 'Unknown Game'
    #     db_manager.add_user_game(user_db_id, game_db_id, source)
    #     success_msg = f"Successfully added **{game_title}** from **{source}** to your library!"
    #     await interaction.followup.send(success_msg)

    @app_commands.command(name="add_games", description="Adds multiple games to your library for a single platform.")
    @app_commands.describe(
        platform="The platform you own these games on.",
        game_1="The first game to add to your library.",
        game_2="The second game to add to your library.",
        game_3="The third game to add to your library.",
        game_4="The fourth game to add to your library.",
        game_5="The fifth game to add to your library."
    )
    async def add_games(
        self,
        interaction: discord.Interaction,
        platform: str,
        game_1: int,
        game_2: int = None,
        game_3: int = None,
        game_4: int = None,
        game_5: int = None,
    ):
        await interaction.response.defer(ephemeral=True)

        game_ids = [g for g in [game_1, game_2, game_3, game_4, game_5] if g is not None]

        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)

        added_game_names = []
        for igdb_id in game_ids:
            game_db_id = await db_manager.add_game(igdb_id=igdb_id)
            if game_db_id:
                db_manager.add_user_game(user_db_id, game_db_id, platform)
                game_obj = db_manager.get_game_by_igdb_id(igdb_id)
                if game_obj:
                    added_game_names.append(game_obj.title)

        if added_game_names:
            confirmation_msg = f"Successfully added the following games to your library: {', '.join(added_game_names)} on {platform}!"
        else:
            confirmation_msg = "No games were added."

        await interaction.followup.send(confirmation_msg)

    # @add_games.autocomplete('name')
    @add_games.autocomplete('game_1')
    @add_games.autocomplete('game_2')
    @add_games.autocomplete('game_3')
    @add_games.autocomplete('game_4')
    @add_games.autocomplete('game_5')
    async def game_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for game names from local DB and IGDB."""
        if not current:
            return []
        try:
            # Hybrid search: local first, then IGDB
            local_games = db_manager.search_games_by_name(current)
            choices = {game.igdb_id: app_commands.Choice(name=game.title, value=game.igdb_id) for game in local_games}

            # Supplement with IGDB search, avoiding duplicates
            if len(choices) < 25:
                igdb_games = await igdb_api.search_games(current)
                for game in igdb_games:
                    if game['id'] not in choices:
                        choices[game['id']] = app_commands.Choice(name=game['name'], value=game['id'])
                    if len(choices) >= 25:
                        break

            return list(choices.values())[:25]
        except Exception as e:
            logger.error(f"Error in game_autocomplete: {e}")
            return []

    # @add_game.autocomplete('source')
    @add_games.autocomplete('platform')
    async def source_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for source names."""
        sources = ["PC", "Steam", "Xbox", "PlayStation", "Switch", "GOG"]
        return [app_commands.Choice(name=s, value=s) for s in sources if current.lower() in s.lower()]




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
            user_game = db_manager.get_user_game_ownership(self.user_id, game.igdb_id)
            owned = user_game is not None
            installed = user_game.is_installed if owned else False
            current_row = i // 2
            owned_label = f"{game.title} - Owned"
            owned_style = discord.ButtonStyle.success if owned else discord.ButtonStyle.secondary
            owned_button = discord.ui.Button(
                label=owned_label[:80], custom_id=f"toggle_owned_{game.igdb_id}",
                style=owned_style, row=current_row
            )
            self.add_item(owned_button)
            installed_label = "Installed" if installed else "Not Installed"
            installed_style = discord.ButtonStyle.blurple if installed else discord.ButtonStyle.grey
            installed_button = discord.ui.Button(
                label=installed_label, custom_id=f"toggle_installed_{game.igdb_id}",
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
                user_game = db_manager.get_user_game_ownership(self.user_id, game.igdb_id)
                owned_emoji = '✅' if user_game else '❌'
                installed_emoji = '✅' if user_game and user_game.is_installed else '❌'
                field_text.append(f"**{game.title}** (Owned: {owned_emoji} | Installed: {installed_emoji})")
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
                    db_manager.add_user_game(self.user_id, game_id, "manual") # Default to manual if adding via this command
            elif sub_action == "installed":
                if user_game:
                    db_manager.set_user_game_installed(self.user_id, game_id, not user_game.is_installed)
        self.build_view()
        new_embed = await self.create_embed()
        await interaction.edit_original_response(embed=new_embed, view=self)
