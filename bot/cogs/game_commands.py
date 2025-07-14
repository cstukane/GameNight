import re
from datetime import datetime

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

    def __init__(self, suggested_games):
        """Initialize the view for game suggestions.

        Args:
        ----
            suggested_games (list): A list of suggested game objects.

        """
        super().__init__(timeout=180)  # Timeout after 3 minutes
        self.suggested_games = suggested_games
        self.add_item(discord.ui.Button(label="Create Poll", style=discord.ButtonStyle.green, custom_id="create_poll"))

        # Add a launch button for each of the top 3 suggested games
        for game in suggested_games[:3]:
            if game.steam_appid:  # Only add launch button if it's a Steam game
                self.add_item(discord.ui.Button(
                    label=f"Launch {game.name}",
                    style=discord.ButtonStyle.blurple,
                    custom_id=f"launch_game_{game.id}"
                ))

    async def on_button_click(self, interaction: discord.Interaction):
        """Handle button clicks for creating polls or launching games."""
        custom_id = interaction.data["custom_id"]
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))

        if custom_id == "create_poll":
            # Placeholder for poll creation logic
            await interaction.response.send_message("Poll creation logic will go here!", ephemeral=True)

        elif custom_id.startswith("launch_game_"):
            game_id = int(custom_id.replace("launch_game_", ""))
            game = Game.get_by_id(game_id)

            if not user_db:
                await interaction.response.send_message(
                    "You are not registered. Please add a game first using /add_game.", ephemeral=True
                )
                return

            user_game_ownership = db_manager.get_user_game_ownership(user_db.id, game_id)

            if user_game_ownership and game:
                if user_game_ownership.platform == "PC" and game.steam_appid:
                    launch_url = f"steam://run/{game.steam_appid}"
                    await interaction.response.send_message(
                        f"Click here to launch **{game.name}**: <{launch_url}>", ephemeral=True
                    )
                else:
                    msg = (f"You own **{game.name}** on {user_game_ownership.platform}. "
                           "Please launch it from the Xbox app or your console.")
                    await interaction.response.send_message(msg, ephemeral=True)
            else:
                msg = (f"It looks like you don't have **{game.name}** in your library. "
                       "Please add it with `/add_game`.")
                await interaction.response.send_message(msg, ephemeral=True)


class GameBrowserView(discord.ui.View):
    """An interactive view for browsing a list of games with grid and detail pages."""

    def __init__(self, games, original_user_id, bot, games_per_page=9, target_user=None,
                 min_players_filter=None, max_players_filter=None, tags_filter=None,
                 unplayed_filter=False, installed_filter=False):
        """Initialize the game browser view with optional filters.

        Args:
        ----
            games (list): The list of game objects to display.
            original_user_id (int): The discord ID of the user who invoked the command.
            bot (commands.Bot): The bot instance, for fetching user data.
            games_per_page (int, optional): The number of games per grid page. Defaults to 9.
            target_user (discord.User, optional): The user whose library is being viewed. Defaults to None.
            min_players_filter (int, optional): Filter for minimum players. Defaults to None.
            max_players_filter (int, optional): Filter for maximum players. Defaults to None.
            tags_filter (str, optional): Comma-separated tags to filter by. Defaults to None.
            unplayed_filter (bool, optional): Filter for games not played recently. Defaults to False.
            installed_filter (bool, optional): Filter for installed games. Defaults to False.

        """
        super().__init__(timeout=300)
        self.all_games = games
        self.original_user_id = original_user_id
        self.bot = bot
        self.games_per_page = games_per_page
        self.current_page = 0
        self.selected_game_id = None
        self.message = None
        self.target_user = target_user

        self.min_players_filter = min_players_filter
        self.max_players_filter = max_players_filter
        self.tags_filter = [tag.strip().lower() for tag in tags_filter.split(',')] if tags_filter else []
        self.unplayed_filter = unplayed_filter
        self.installed_filter = installed_filter

        self.filtered_games = self._apply_filters(self.all_games)
        self.all_games = self.filtered_games  # Update all_games to be the filtered list

    def _apply_filters(self, games_list):
        """Apply filters to the list of games and return the filtered list."""
        filtered = []
        for game in games_list:
            # Min Players Filter
            if self.min_players_filter is not None and \
               (game.min_players is None or game.min_players < self.min_players_filter):
                continue

            # Max Players Filter
            if self.max_players_filter is not None and \
               (game.max_players is None or game.max_players < self.max_players_filter):
                continue

            # Tags Filter
            if self.tags_filter:
                game_tags = [tag.strip().lower() for tag in game.tags.split(',')] if game.tags else []
                if not any(ftag in game_tags for ftag in self.tags_filter):
                    continue

            # User-specific filters (unplayed, installed)
            if self.unplayed_filter or self.installed_filter:
                user_id_str = str(self.target_user.id) if self.target_user else str(self.original_user_id)
                user_db = db_manager.get_user_by_discord_id(user_id_str)

                if not user_db:
                    # If a user-specific filter is active but the user is not in the database,
                    # then this game cannot match, so we skip it.
                    continue

                user_game_ownership = db_manager.get_user_game_ownership(user_db.id, game.id)

                # Unplayed Filter: Skip if the game has been recently played.
                if self.unplayed_filter:
                    # A game is considered "recently played" only if the user owns it and it has a recent play date.
                    if user_game_ownership and game.last_played and (datetime.now() - game.last_played).days < 30:
                        continue

                # Installed Filter: Skip if the game is not installed.
                if self.installed_filter:
                    # A game can only be "installed" if the user owns it and it's marked as such.
                    if not (user_game_ownership and user_game_ownership.is_installed):
                        continue

            filtered.append(game)
        return filtered

    async def create_game_embed(self) -> discord.Embed:
        """Create the embed for the current view (grid or detail).

        Returns
        -------
            discord.Embed: The embed to display.

        """
        if self.selected_game_id:
            return await self._create_detail_embed()
        return await self._create_grid_embed()

    async def _create_detail_embed(self) -> discord.Embed:
        """Create the embed for the detailed game view."""
        game = next((g for g in self.all_games if g.id == self.selected_game_id), None)
        if not game:
            return discord.Embed(
                title="Game Not Found",
                description="Could not retrieve game details.",
                color=discord.Color.red()
            )

        embed = discord.Embed(
            title=game.name,
            description=game.description or "No description available.",
            color=discord.Color.purple()
        )
        cover_art_url = get_game_image(game.name, image_type="hero")
        if cover_art_url:
            embed.set_image(url=cover_art_url)

        embed.add_field(name="Players", value=f"{game.min_players or '?'} - {game.max_players or '?'}", inline=True)
        embed.add_field(name="Tags", value=game.tags or "N/A", inline=True)
        embed.add_field(name="Release Date", value=game.release_date or "N/A", inline=True)

        owners_info = db_manager.get_game_owners_with_platforms(game.id)
        if owners_info:
            owner_list = []
            for owner_discord_id, platform in owners_info:
                owner_user = self.bot.get_user(int(owner_discord_id))
                owner_name = owner_user.display_name if owner_user else f"User {owner_discord_id}"
                owner_list.append(f"{owner_name} ({platform})")
            embed.add_field(name="Owners", value="\n".join(owner_list), inline=False)
        else:
            embed.add_field(name="Owners", value="No one owns this game.", inline=False)

        return embed

    async def _create_grid_embed(self) -> discord.Embed:
        """Create the embed for the grid view of games."""
        start_index = self.current_page * self.games_per_page
        end_index = min(start_index + self.games_per_page, len(self.all_games))
        games_on_page = self.all_games[start_index:end_index]

        if self.target_user:
            title = f"**{self.target_user.display_name}'s Game Library:**"
        else:
            title = f"Game Library (Page {self.current_page + 1}/{self.total_pages()})"

        embed = discord.Embed(
            title=title,
            description="Click a button below to see that game's details.",
            color=discord.Color.blue()
        )

        if games_on_page:
            first_game_cover = get_game_image(games_on_page[0].name, image_type="grid")
            if first_game_cover:
                embed.set_thumbnail(url=first_game_cover)
        else:
            embed.description = "No games found on this page."

        return embed

    def total_pages(self):
        """Calculate the total number of pages."""
        return (len(self.all_games) + self.games_per_page - 1) // self.games_per_page

    async def update_view(self, interaction: discord.Interaction):
        """Update the view with the correct buttons and embed."""
        self.clear_items()
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))

        if self.selected_game_id:
            # Detail View Buttons
            game = next((g for g in self.all_games if g.id == self.selected_game_id), None)
            if game and user_db:
                user_game_ownership = db_manager.get_user_game_ownership(user_db.id, game.id)
                liked = user_game_ownership and user_game_ownership.liked
                disliked = user_game_ownership and user_game_ownership.disliked
                like_style = discord.ButtonStyle.success if liked else discord.ButtonStyle.secondary
                dislike_style = discord.ButtonStyle.danger if disliked else discord.ButtonStyle.secondary
                self.add_item(discord.ui.Button(label="❤️ Like", custom_id=f"like_{game.id}", style=like_style))
                self.add_item(discord.ui.Button(label="💔 Dislike", custom_id=f"dislike_{game.id}", style=dislike_style))

            self.add_item(discord.ui.Button(label="Back to Grid", custom_id="back_to_grid", row=1))
        else:
            # Grid View Buttons
            start_index = self.current_page * self.games_per_page
            end_index = min(start_index + self.games_per_page, len(self.all_games))
            games_on_page = self.all_games[start_index:end_index]

            for game in games_on_page:
                self.add_item(discord.ui.Button(label=game.name, custom_id=f"game_detail_{game.id}"))

            nav_row = discord.ui.ActionRow()
            if self.current_page > 0:
                nav_row.add_item(discord.ui.Button(label="Previous", custom_id="prev_page"))
            if self.current_page < self.total_pages() - 1:
                nav_row.add_item(discord.ui.Button(label="Next", custom_id="next_page"))
            if nav_row.children:
                self.add_item(nav_row)

        embed = await self.create_game_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_button_click(self, interaction: discord.Interaction):
        """Handle button clicks for navigation and interaction."""
        custom_id = interaction.data["custom_id"]
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))

        if custom_id == "prev_page":
            self.current_page -= 1
        elif custom_id == "next_page":
            self.current_page += 1
        elif custom_id.startswith("game_detail_"):
            self.selected_game_id = int(custom_id.replace("game_detail_", ""))
        elif custom_id == "back_to_grid":
            self.selected_game_id = None
        elif custom_id.startswith(("like_", "dislike_")):
            if not user_db:
                await interaction.response.send_message(
                    "You need to add a game to your library first!", ephemeral=True
                )
                return
            action, game_id_str = custom_id.split("_", 1)
            game_id = int(game_id_str)
            db_manager.set_game_liked_status(user_db.id, game_id, like=(action == "like"))

        await self.update_view(interaction)


class GameCommands(commands.Cog):
    """A cog for all game-related commands."""

    def __init__(self, bot):
        """Initialize the GameCommands cog.

        Args:
        ----
            bot (commands.Bot): The instance of the bot.

        """
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle errors for commands in this cog."""
        if isinstance(error, (GameNightError, GameNotFoundError, UserNotFoundError)):
            await interaction.followup.send(str(error), ephemeral=True)
        else:
            logger.error(f"An unexpected error occurred in GameCommands: {error}")
            await interaction.followup.send("An unexpected error occurred. Please try again later.", ephemeral=True)
            raise error

    @app_commands.command(name="suggest_games", description="Suggests games for the group.")
    @app_commands.describe(
        group_size="The number of players in your group.",
        preferred_tags="A comma-separated list of preferred tags.",
        users="Mention specific users to include in the suggestion (e.g., @user1 @user2)."
    )
    async def suggest(
        self, interaction: discord.Interaction, group_size: int = None,
        preferred_tags: str = None, users: str = None
    ):
        """Suggest games that everyone in the group owns and displays them in a rich embed."""
        await interaction.response.defer()

        available_user_ids = []
        if users:
            # Parse user IDs from mentions in the string
            user_mentions = re.findall(r'<@!?(\d+)>', users)
            for user_id_str in user_mentions:
                user_db = db_manager.get_user_by_discord_id(user_id_str)
                if user_db:
                    available_user_ids.append(user_db.id)
                else:
                    # Attempt to get user by ID if not found in DB (e.g., new user)
                    discord_user = self.bot.get_user(int(user_id_str))
                    if discord_user:
                        msg = (f"Warning: {discord_user.display_name} is not registered and will be "
                               "excluded from suggestions.")
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        msg = f"Warning: User with ID {user_id_str} not found and will be excluded from suggestions."
                        await interaction.followup.send(msg, ephemeral=True)

            if not available_user_ids:
                raise UserNotFoundError(
                    "None of the specified users are registered or found. "
                    "Please ensure they have added games first."
                )
        else:
            all_users = db_manager.get_all_users()
            if not all_users:
                raise UserNotFoundError("No users found. Please add some users and games first.")
            available_user_ids = [user.id for user in all_users]

        tags = preferred_tags.split(',') if preferred_tags else None
        suggested_games = suggest_games(available_user_ids, group_size=group_size, preferred_tags=tags)

        if not suggested_games:
            raise GameNotFoundError("I couldn't find any suitable games for your group.")

        embed = discord.Embed(
            title="Tonight's Game Suggestions",
            description="Here are the top picks based on your group's libraries and preferences.",
            color=discord.Color.purple()
        )

        for game in suggested_games[:3]:
            value = f"Players: {game.min_players or '?'}\nTags: {game.tags or 'N/A'}"
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
        platform="The platform you own the game on (e.g., PC, Xbox, Switch).",
        steam_appid="The Steam App ID of the game (if applicable).",
        min_players="Minimum number of players for the game.",
        max_players="Maximum number of players for the game."
    )
    async def add_game(
        self,
        interaction: discord.Interaction,
        name: str,
        platform: str,
        steam_appid: int = None,
        min_players: int = None,
        max_players: int = None
    ):
        """Add a game to the user's library, fetching details from Steam if an app ID is provided."""
        await interaction.response.defer(ephemeral=True)

        if platform not in ALLOWED_PLATFORMS:
            raise GameNightError(
                f"Invalid platform. Please choose from: {', '.join(ALLOWED_PLATFORMS)}"
            )

        details = get_game_details(steam_appid) if steam_appid else None
        tags, release_date, description = None, None, None

        if details:
            name = details.get('name', name)
            genres = details.get('genres', [])
            tags = ",".join([tag['description'] for tag in genres])
            min_players = details.get('min_players', min_players)
            max_players = details.get('max_players', max_players)
            release_date = details.get('release_date', {}).get('date')
            description = details.get('short_description')
        elif steam_appid and not details:
            await interaction.followup.send("Could not fetch details from Steam. Storing with provided info.")

        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        if user_db_id is None:
            raise UserNotFoundError("There was an error adding you to the database.")

        game_db_id = db_manager.add_game(
            name, steam_appid, tags, min_players, max_players, release_date, description
        )
        if game_db_id is None:
            raise GameNotFoundError("There was an error adding the game to the database.")

        db_manager.add_user_game(user_db_id, game_db_id, platform)
        await interaction.followup.send(f"Successfully added **{name}** on **{platform}** to your library!")

    @app_commands.command(name="view_games", description="Displays all games in the database.")
    @app_commands.describe(
        min_players="Minimum number of players for the game.",
        max_players="Maximum number of players for the game.",
        tags="Comma-separated list of tags (e.g., 'Action,RPG')."
    )
    async def view_games(self, interaction: discord.Interaction, min_players: int = None, max_players: int = None, tags: str = None):
        """Display all games in the database in an interactive browser with optional filters."""
        await interaction.response.defer()
        all_games = db_manager.get_all_games()
        if not all_games:
            raise GameNotFoundError("No games found. Add some with `/add_game`!")

        all_games.sort(key=lambda game: game.name.lower())
        view = GameBrowserView(
            all_games, interaction.user.id, self.bot,
            min_players_filter=min_players, max_players_filter=max_players, tags_filter=tags
        )
        embed = await view.create_game_embed()
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message

    @app_commands.command(name="view_library", description="Displays a user's game library.")
    @app_commands.describe(
        user="The user whose library you want to view. Defaults to yourself.",
        min_players="Minimum number of players for the game.",
        max_players="Maximum number of players for the game.",
        tags="Comma-separated list of tags (e.g., 'Action,RPG').",
        unplayed="True to show games not played recently.",
        installed="True to show only installed games."
    )
    async def view_library(
        self, interaction: discord.Interaction, user: discord.Member = None,
        min_players: int = None, max_players: int = None, tags: str = None,
        unplayed: bool = False, installed: bool = False
    ):
        """Display a user's game library in an interactive browser."""
        await interaction.response.defer()
        target_user = user or interaction.user
        user_db = db_manager.get_user_by_discord_id(str(target_user.id))
        if not user_db:
            raise UserNotFoundError(f"{target_user.display_name} has not added any games yet.")

        user_games = db_manager.get_user_game_ownerships(user_db.id)
        if not user_games:
            raise GameNotFoundError(f"{target_user.display_name} has no games in their library.")

        games = sorted([ug.game for ug in user_games], key=lambda g: g.name.lower())
        view = GameBrowserView(
            games=games,
            original_user_id=interaction.user.id,
            bot=self.bot,
            target_user=target_user,
            min_players_filter=min_players,
            max_players_filter=max_players,
            tags_filter=tags,
            unplayed_filter=unplayed,
            installed_filter=installed
        )
        embed = await view.create_game_embed()
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message

    @app_commands.command(name="manage_games", description="Manage your game library.")
    async def manage_games(self, interaction: discord.Interaction):
        """Display a view to manage your game library."""
        await interaction.response.defer()
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        if not user_db:
            raise UserNotFoundError("You have not added any games yet.")

        user_games = db_manager.get_user_game_ownerships(user_db.id)
        if not user_games:
            raise GameNotFoundError("You have no games in your library.")

        games = sorted([ug.game for ug in user_games], key=lambda g: g.name.lower())
        view = GameManagementView(games, user_db.id, interaction.user.id)
        embed = discord.Embed(title="Manage Your Games")
        for game in games:
            user_game = db_manager.get_user_game_ownership(user_db.id, game.id)
            owned = user_game is not None
            installed = user_game.is_installed if owned else False
            value = (f"Owned: {'✅' if owned else '❌'}\n"
                     f"Installed: {'✅' if installed else '❌'}")
            embed.add_field(name=game.name, value=value, inline=False)

        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message

    # --- Autocompleters ---
    @add_game.autocomplete('name')
    async def game_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete game names for the add_game command."""
        games = db_manager.search_games_by_name(current) if current else []
        return [app_commands.Choice(name=game, value=game) for game in games][:25]

    @add_game.autocomplete('platform')
    async def platform_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete platform names for the add_game command."""
        return [
            app_commands.Choice(name=platform, value=platform)
            for platform in ALLOWED_PLATFORMS if current.lower() in platform.lower()
        ]


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(GameCommands(bot))


class GameManagementView(discord.ui.View):
    """A view to manage games in a user's library."""

    def __init__(self, games, user_id, original_interactor_id):
        super().__init__()
        self.games = games
        self.user_id = user_id
        self.original_interactor_id = original_interactor_id
        self.message = None

        for game in self.games:
            user_game = db_manager.get_user_game_ownership(self.user_id, game.id)
            owned = user_game is not None
            installed = user_game.is_installed if owned else False

            owned_label = f"{game.name} - Owned: {'✅' if owned else '❌'}"
            owned_style = discord.ButtonStyle.green if owned else discord.ButtonStyle.red
            self.add_item(discord.ui.Button(
                label=owned_label, custom_id=f"toggle_owned_{game.id}", style=owned_style
            ))

            installed_label = f"Installed: {'✅' if installed else '❌'}"
            installed_style = discord.ButtonStyle.blurple if installed else discord.ButtonStyle.grey
            self.add_item(discord.ui.Button(
                label=installed_label, custom_id=f"toggle_installed_{game.id}",
                style=installed_style, disabled=not owned
            ))

    async def on_button_click(self, interaction: discord.Interaction):
        """Handle button clicks to toggle game ownership or installed status."""
        custom_id = interaction.data["custom_id"]
        action, sub_action, game_id_str = custom_id.split("_")
        game_id = int(game_id_str)

        if action == "toggle":
            sub_action = custom_id.split("_")[1]
            if sub_action == "owned":
                user_game = db_manager.get_user_game_ownership(self.user_id, game_id)
                if user_game:
                    db_manager.remove_user_game(self.user_id, game_id)
                else:
                    db_manager.add_user_game(self.user_id, game_id, "PC")
            elif sub_action == "installed":
                user_game = db_manager.get_user_game_ownership(self.user_id, game_id)
                if user_game:
                    db_manager.set_user_game_installed(self.user_id, game_id, not user_game.is_installed)

        await self.update_view(interaction)

    async def update_view(self, interaction: discord.Interaction):
        """Refresh the view with updated game information."""
        embed = discord.Embed(title="Manage Your Games")
        for game in self.games:
            user_game = db_manager.get_user_game_ownership(self.user_id, game.id)
            owned = user_game is not None
            installed = user_game.is_installed if owned else False
            value = (f"Owned: {'✅' if owned else '❌'}\n"
                     f"Installed: {'✅' if installed else '❌'}")
            embed.add_field(name=game.name, value=value, inline=False)

        await interaction.response.edit_message(embed=embed, view=self)
