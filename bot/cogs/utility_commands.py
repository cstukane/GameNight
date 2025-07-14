# Standard library imports
from datetime import datetime

# Third-party imports
import discord
from discord import app_commands
from discord.ext import commands
from peewee import fn

# Local application imports
from bot.cogs.game_commands import GameBrowserView
from data import db_manager
from data.models import VoiceActivity
from steam.fetch_library import fetch_and_store_games
from utils.errors import UserNotFoundError


class UtilityCommands(commands.Cog):
    """A cog for utility and profile-related commands."""

    def __init__(self, bot):
        """Initialize the UtilityCommands cog."""
        self.bot = bot

    @app_commands.command(name="ping", description="Responds with Pong!")
    async def ping(self, interaction: discord.Interaction):
        """Check if the bot is responsive."""
        await interaction.response.send_message("Pong!")

    @app_commands.command(name="profile", description="Displays a user's profile and game library.")
    @app_commands.describe(
        user="The user whose profile you want to view. Defaults to yourself.",
        min_players="Minimum number of players for the game.",
        max_players="Maximum number of players for the game.",
        tags="Comma-separated list of tags (e.g., 'Action,RPG').",
        unplayed="True to show games not played recently.",
        installed="True to show only installed games."
    )
    async def profile(
        self, interaction: discord.Interaction, user: discord.Member = None,
        min_players: int = None, max_players: int = None, tags: str = None,
        unplayed: bool = False, installed: bool = False
    ):
        """Display a user's profile, including an interactive view of their games."""
        await interaction.response.defer()

        target_user = user or interaction.user

        user_db = db_manager.get_user_by_discord_id(str(target_user.id))
        if not user_db:
            raise UserNotFoundError(f"{target_user.display_name} does not have a profile yet.")

        # Display the interactive game library view, which is the core of the profile
        user_games = db_manager.get_user_game_ownerships(user_db.id)
        if not user_games:
            await interaction.followup.send(f"{target_user.display_name} has no games in their library.")
            return

        games = sorted([ug.game for ug in user_games], key=lambda g: g.name.lower())
        view = GameBrowserView(
            games, interaction.user.id, self.bot, target_user=target_user,
            min_players_filter=min_players, max_players_filter=max_players, tags_filter=tags,
            unplayed_filter=unplayed, installed_filter=installed
        )

        # Create a simple top-level embed for the profile
        embed = discord.Embed(
            title=f"{target_user.display_name}'s Profile",
            description=f"Showing the game library for {target_user.mention}. "
                        "Use the buttons below to browse.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)

        browser_embed = await view.create_game_embed()
        # Combine the initial embed and the browser view into a single message
        message = await interaction.followup.send(embeds=[embed, browser_embed], view=view)
        view.message = message

    @app_commands.command(name="set_steam_id", description="Sets your Steam ID for automatic library syncing.")
    @app_commands.describe(steam_id="Your 64-bit Steam ID.")
    async def set_steam_id(self, interaction: discord.Interaction, steam_id: str):
        """Link a user's Steam ID and fetch their game library with improved guidance."""
        await interaction.response.defer(ephemeral=True)

        if not steam_id.isdigit() or len(steam_id) != 17:
            help_message = (
                "**Invalid Steam ID format.**\n"
                "Please provide your **64-bit Steam ID**, which is a 17-digit number.\n\n"
                "**How to find your Steam ID:**\n"
                "1. Go to a site like [SteamID.io](https://steamid.io/).\n"
                "2. Enter your Steam profile name or URL.\n"
                "3. Look for the value labeled **steamID64**."
            )
            await interaction.followup.send(help_message, ephemeral=True)
            return

        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        if user_db_id is None:
            await interaction.followup.send("Error adding you to the database. Please try again.", ephemeral=True)
            return
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        if user_db is None:  # Should not happen if add_user was successful
            await interaction.followup.send("Error retrieving user from database. Please try again.", ephemeral=True)
            return

        db_manager.set_steam_id(user_db.id, steam_id)
        await fetch_and_store_games(user_db.id, steam_id)
        await interaction.followup.send("Your Steam library has been successfully synced!", ephemeral=True)

    @app_commands.command(name="help", description="Displays a list of all available commands.")
    async def help(self, interaction: discord.Interaction):
        """Show a detailed list of all available commands."""
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="Game Night Bot Help",
            description="Here's how you can use me to organize your game nights:",
            color=discord.Color.blue()
        )

        general_commands_desc = (
            "**/ping** - Check if the bot is online.\n"
            "**/profile `[user]`** - View a user's profile and interactive game library.\n"
            "**/set_steam_id `<steam_id>`** - Link your Steam account to auto-sync your library.\n"
            "**/set_reminder_offset `<minutes>`** - Set your preferred reminder time before a game night."
        )
        embed.add_field(name="General & Profile", value=general_commands_desc, inline=False)

        game_commands_desc = (
            "**/add_game** - Manually add a game to your library.\n"
            "**/view_games** - See all games in the database in an interactive browser.\n"
            "**/view_library `[user]`** - View your own or another user's game library browser.\n"
            "*Use the ❤️ and 💔 buttons in the library browser to like/dislike games.*"
        )
        embed.add_field(name="Game Management", value=game_commands_desc, inline=False)

        gamenight_commands_desc = (
            "**/next_game_night `<date>` `<time>`** - Schedule a new game night and start a poll.\n"
            "**/set_game_night_availability `<id>` `<status>`** - Set your availability for a game night.\n"
            "**/set_weekly_availability** - Set your recurring available days for game nights.\n"
            "**/finalize_game_night `<id>`** - (Organizer only) Finalize attendees and start the game poll."
        )
        embed.add_field(name="Game Night Organization", value=gamenight_commands_desc, inline=False)

        embed.set_footer(text="Use slash commands to see options. Find your Steam ID at steamid.io.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="set_weekly_availability", description="Set your recurring weekly availability for game nights.")
    @app_commands.describe(
        available_days="Comma-separated day names (e.g., 'Monday,Wednesday') or numbers (0=Monday, 6=Sunday)."
    )
    async def set_weekly_availability(self, interaction: discord.Interaction, available_days: str):
        """Set a user's weekly availability, converting day names to numbers if necessary."""
        await interaction.response.defer(ephemeral=True)

        day_mapping = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }

        # Normalize input: convert day names to numbers
        processed_days = []
        input_days = [d.strip().lower() for d in available_days.split(',')]

        if "none" in input_days:
            # If 'none' is explicitly provided, clear availability
            final_availability_string = ""
            display_message = "none"
        else:
            for day in input_days:
                if day.isdigit() and 0 <= int(day) <= 6:
                    processed_days.append(day)
                elif day in day_mapping:
                    processed_days.append(str(day_mapping[day]))
                else:
                    await interaction.followup.send(
                        f"Invalid day '{day}'. Please use day names (e.g., 'Monday') or numbers (0-6).",
                        ephemeral=True
                    )
                    return
            unique_sorted_days = sorted(list(set(processed_days)))
            final_availability_string = ",".join(unique_sorted_days)
            display_message = available_days  # Display original input for user clarity

        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        db_manager.set_user_weekly_availability(user_db_id, final_availability_string)
        await interaction.followup.send(f"Your weekly availability has been set to: **{display_message}**.", ephemeral=True)

    @app_commands.command(name="set_game_pass", description="Set your Game Pass status.")
    @app_commands.describe(
        has_game_pass="True if you have Game Pass, False otherwise."
    )
    async def set_game_pass(self, interaction: discord.Interaction, has_game_pass: bool):
        """Set a user's Game Pass status."""
        await interaction.response.defer(ephemeral=True)
        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        db_manager.set_user_game_pass_status(user_db_id, has_game_pass)
        status = "enabled" if has_game_pass else "disabled"
        await interaction.followup.send(f"Your Game Pass status has been set to **{status}**.", ephemeral=True)

    @app_commands.command(name="set_reminder_offset", description="Set your default game night reminder offset.")
    @app_commands.describe(offset_minutes="The time before a game night to send a reminder.")
    @app_commands.choices(offset_minutes=[
        app_commands.Choice(name="15 Minutes", value=15),
        app_commands.Choice(name="30 Minutes", value=30),
        app_commands.Choice(name="45 Minutes", value=45),
        app_commands.Choice(name="1 Hour", value=60),
        app_commands.Choice(name="1 Hour 15 Minutes", value=75),
        app_commands.Choice(name="1 Hour 30 Minutes", value=90),
        app_commands.Choice(name="2 Hours", value=120),
        app_commands.Choice(name="3 Hours", value=180),
        app_commands.Choice(name="6 Hours", value=360),
        app_commands.Choice(name="12 Hours", value=720),
        app_commands.Choice(name="24 Hours", value=1440),
    ])
    async def set_reminder_offset(self, interaction: discord.Interaction, offset_minutes: app_commands.Choice[int]):
        """Set a user's default reminder time before a game night using a dropdown."""
        await interaction.response.defer(ephemeral=True)

        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        if not user_db:
            raise UserNotFoundError(
                "You are not registered. Please add a game first using /add_game."
            )

        selected_offset = offset_minutes.value
        db_manager.set_user_reminder_offset(user_db.id, selected_offset)
        await interaction.followup.send(f"Your default reminder offset has been set to **{offset_minutes.name}**.", ephemeral=True)

    @app_commands.command(name="discord_wrapped", description="Shows your voice activity statistics for a year.")
    @app_commands.describe(year="The year for which to show statistics (defaults to current year).")
    async def discord_wrapped(self, interaction: discord.Interaction, year: int = None):
        """Display a user's voice chat statistics for a given year."""
        await interaction.response.defer()

        target_year = year or datetime.now().year
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        if not user_db:
            raise UserNotFoundError("You don't have any recorded activity yet.")

        start_date = datetime(target_year, 1, 1)
        end_date = datetime(target_year + 1, 1, 1)

        # Calculate total time spent in voice channels
        total_time_seconds = VoiceActivity.select(fn.SUM(VoiceActivity.duration_seconds)).where(
            VoiceActivity.user == user_db,
            VoiceActivity.join_time >= start_date,
            VoiceActivity.join_time < end_date,
            VoiceActivity.duration_seconds.is_null(False)
        ).scalar() or 0
        total_hours = round(total_time_seconds / 3600, 2)

        # Count unique days joined
        unique_days = VoiceActivity.select(fn.COUNT(fn.DISTINCT(fn.date(VoiceActivity.join_time)))).where(
            VoiceActivity.user == user_db,
            VoiceActivity.join_time >= start_date,
            VoiceActivity.join_time < end_date
        ).scalar() or 0

        # Count total joins
        total_joins = VoiceActivity.select().where(
            VoiceActivity.user == user_db,
            VoiceActivity.join_time >= start_date,
            VoiceActivity.join_time < end_date
        ).count()

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Discord Wrapped {target_year}",
            color=discord.Color.purple()
        )
        embed.add_field(name="Total Time in Voice", value=f"{total_hours} hours", inline=False)
        embed.add_field(name="Days Joined Voice", value=f"{unique_days} days", inline=False)
        # Count game nights attended
        game_nights_attended = db_manager.get_attended_game_nights_count(user_db.id, start_date, end_date)

        embed.add_field(name="Total Joins", value=f"{total_joins} times", inline=False)
        embed.add_field(name="Game Nights Attended", value=f"{game_nights_attended} nights", inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="game_night_history", description="Shows a user's past game night attendance.")
    @app_commands.describe(user="The user whose game night history you want to view. Defaults to yourself.")
    async def game_night_history(self, interaction: discord.Interaction, user: discord.Member = None):
        """Display a user's game night attendance history."""
        await interaction.response.defer()

        target_user = user or interaction.user
        user_db = db_manager.get_user_by_discord_id(str(target_user.id))

        if not user_db:
            raise UserNotFoundError(f"{target_user.display_name} has no recorded game night history.")

        game_nights = db_manager.get_user_game_night_history(user_db.id)

        embed = discord.Embed(
            title=f"{target_user.display_name}'s Game Night History",
            color=discord.Color.green()
        )

        if not game_nights:
            embed.description = "No game nights attended yet."
        else:
            description_lines = []
            for gn in game_nights:
                game_name = gn.selected_game.name if gn.selected_game else "(Game not selected)"
                scheduled_time_str = gn.scheduled_time.strftime('%Y-%m-%d %I:%M %p')
                description_lines.append(f"**{scheduled_time_str}**: {game_name}")
            embed.description = "\n".join(description_lines[:10])  # Show up to 10 recent game nights
            if len(description_lines) > 10:
                footer_text = (
                    f"Showing {len(description_lines[:10])} of {len(description_lines)} "
                    "game nights. More available in logs."
                )
                embed.set_footer(text=footer_text)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="set_main_channel", description="Sets the main channel for polls and announcements.")
    @app_commands.describe(channel="The channel to set as the main channel.")
    @app_commands.default_permissions(manage_guild=True)
    async def set_main_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the designated channel for main announcements and polls."""
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db_manager.set_guild_main_channel(str(interaction.guild.id), str(channel.id))
        await interaction.followup.send(f"Main channel has been set to {channel.mention}.")


async def setup(bot):
    """Set up the cog and add it to the bot."""
    await bot.add_cog(UtilityCommands(bot))
