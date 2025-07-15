import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from peewee import fn

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
        """Check if the bot is online."""
        await interaction.response.send_message("Pong!", ephemeral=True)

    @app_commands.command(name="profile", description="Displays a user's profile and a link to their game library.")
    @app_commands.describe(user="The user whose profile you want to view. Defaults to yourself.")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        """Display a user's profile with stats and a link to their web library."""
        await interaction.response.defer()

        target_user = user or interaction.user
        user_db = db_manager.get_user_by_discord_id(str(target_user.id))
        if not user_db:
            raise UserNotFoundError(f"{target_user.display_name} does not have a profile yet.")

        # --- Profile Stats ---
        games_count = len(db_manager.get_user_game_ownerships(user_db.id))
        game_pass_status = "Yes" if user_db.has_game_pass else "No"

        embed = discord.Embed(
            title=f"{target_user.display_name}'s Profile",
            color=target_user.color,
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.add_field(name="Total Games Owned", value=str(games_count), inline=True)
        embed.add_field(name="Has Game Pass", value=game_pass_status, inline=True)

        # --- Link to Web Library ---
        base_url = os.getenv("BASE_URL")
        view = discord.ui.View()

        if base_url:
            library_url = f"{base_url}/library/{target_user.id}"
            view.add_item(
                discord.ui.Button(label="Browse Full Game Library", style=discord.ButtonStyle.link, url=library_url)
            )
        else:
            embed.set_footer(text="Web library link is not configured by the bot owner.")

        await interaction.followup.send(embed=embed, view=view)

    # ... the rest of the file (set_steam_id, help, etc.) remains the same ...

    @app_commands.command(name="set_steam_id", description="Sets your Steam ID for automatic library syncing.")
    @app_commands.describe(steam_id="Your 64-bit Steam ID.")
    async def set_steam_id(self, interaction: discord.Interaction, steam_id: str):
        """Set a user's Steam ID and sync their library."""
        await interaction.response.defer(ephemeral=True)
        if not steam_id.isdigit() or len(steam_id) != 17:
            help_message = (
                "**Invalid Steam ID format.**\nPlease provide your **64-bit Steam ID**, which is a 17-digit number.\n\n"
                "**How to find your Steam ID:**\n1. Go to a site like [SteamID.io](https://steamid.io/).\n"
                "2. Enter your Steam profile name or URL.\n3. Look for the value labeled **steamID64**."
            )
            await interaction.followup.send(help_message, ephemeral=True)
            return
        user_db = db_manager.add_user(str(interaction.user.id), interaction.user.display_name, steam_id=steam_id)
        await fetch_and_store_games(user_db, steam_id)
        await interaction.followup.send("Your Steam library has been successfully synced!", ephemeral=True)

    @app_commands.command(name="help", description="Displays a list of all available commands.")
    async def help(self, interaction: discord.Interaction):
        """Show a help message with a list of commands."""
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="Game Night Bot Help", description="Here's how you can use me:", color=discord.Color.blue()
        )
        general_commands_desc = (
            "**/ping** - Check if the bot is online.\n"
            "**/profile `[user]`** - View a user's profile and game library link.\n"
            "**/set_steam_id `<steam_id>`** - Link your Steam account.\n"
            "**/set_reminder_offset `<minutes>`** - Set your preferred reminder time."
        )
        embed.add_field(name="General & Profile", value=general_commands_desc, inline=False)
        game_commands_desc = (
            "**/add_game** - Manually add a game to your library.\n"
            "**/manage_games** - Manage ownership and installed status of your games.\n"
            "**/view_library `[user]`** - Get a link to a user's web library."
        )
        embed.add_field(name="Game Management", value=game_commands_desc, inline=False)
        gamenight_commands_desc = (
            "**/next_game_night `<date>` `<time>`** - Schedule a new game night.\n"
            "**/set_weekly_availability** - Set your recurring available days."
        )
        embed.add_field(name="Game Night Organization", value=gamenight_commands_desc, inline=False)
        embed.set_footer(text="Find your Steam ID at steamid.io.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="set_weekly_availability", description="Set your recurring weekly availability for game nights.")
    @app_commands.describe(
        available_days="Comma-separated day names (e.g., 'Monday,Wed') or numbers (0=Mon, 6=Sun)."
    )
    async def set_weekly_availability(self, interaction: discord.Interaction, available_days: str):
        """Set a user's recurring weekly availability."""
        await interaction.response.defer(ephemeral=True)
        day_mapping = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        processed_days = []
        input_days = [d.strip().lower() for d in available_days.split(',')]
        if "none" in input_days:
            final_availability_string, display_message = "", "none"
        else:
            for day in input_days:
                if day.isdigit() and 0 <= int(day) <= 6:
                    processed_days.append(day)
                elif day in day_mapping:
                    processed_days.append(str(day_mapping[day]))
                else:
                    await interaction.followup.send(f"Invalid day '{day}'. Use day names or numbers (0-6).", ephemeral=True)
                    return
            final_availability_string = ",".join(sorted(list(set(processed_days))))
            display_message = available_days
        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        db_manager.set_user_weekly_availability(user_db_id, final_availability_string)
        await interaction.followup.send(
            f"Your weekly availability has been set to: **{display_message}**.", ephemeral=True
        )

    @app_commands.command(name="set_game_pass", description="Set your Game Pass status.")
    @app_commands.describe(has_game_pass="True if you have Game Pass, False otherwise.")
    async def set_game_pass(self, interaction: discord.Interaction, has_game_pass: bool):
        """Set a user's Game Pass status in their profile."""
        await interaction.response.defer(ephemeral=True)
        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        db_manager.set_user_game_pass_status(user_db_id, has_game_pass)
        status_text = 'enabled' if has_game_pass else 'disabled'
        await interaction.followup.send(
            f"Your Game Pass status has been set to **{status_text}**.", ephemeral=True
        )

    @app_commands.command(name="set_reminder_offset", description="Set your default game night reminder offset.")
    @app_commands.describe(offset_minutes="The time before a game night to send a reminder.")
    @app_commands.choices(offset_minutes=[
        app_commands.Choice(name="15 Minutes", value=15), app_commands.Choice(name="30 Minutes", value=30),
        app_commands.Choice(name="1 Hour", value=60), app_commands.Choice(name="2 Hours", value=120),
        app_commands.Choice(name="24 Hours", value=1440),
    ])
    async def set_reminder_offset(self, interaction: discord.Interaction, offset_minutes: app_commands.Choice[int]):
        """Set the user's preferred reminder offset for game nights."""
        await interaction.response.defer(ephemeral=True)
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        if not user_db:
            raise UserNotFoundError("You are not registered. Please add a game first.")
        db_manager.set_user_reminder_offset(user_db.id, offset_minutes.value)
        await interaction.followup.send(f"Your reminder offset is set to **{offset_minutes.name}**.", ephemeral=True)

    @app_commands.command(name="discord_wrapped", description="Shows your voice activity statistics for a year.")
    @app_commands.describe(year="The year for which to show statistics (defaults to current year).")
    async def discord_wrapped(self, interaction: discord.Interaction, year: int = None):
        """Show a user's voice activity stats for a given year."""
        await interaction.response.defer()
        target_year = year or datetime.now().year
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        if not user_db:
            raise UserNotFoundError("You don't have any recorded activity yet.")
        start_date, end_date = datetime(target_year, 1, 1), datetime(target_year + 1, 1, 1)
        total_time_seconds = (VoiceActivity
                              .select(fn.SUM(VoiceActivity.duration_seconds))
                              .where(VoiceActivity.user == user_db,
                                     VoiceActivity.join_time >= start_date,
                                     VoiceActivity.join_time < end_date,
                                     VoiceActivity.duration_seconds.is_null(False))
                              .scalar() or 0)
        total_hours = round(total_time_seconds / 3600, 2)
        unique_days = (VoiceActivity
                       .select(fn.COUNT(fn.DISTINCT(fn.date(VoiceActivity.join_time))))
                       .where(VoiceActivity.user == user_db,
                              VoiceActivity.join_time >= start_date,
                              VoiceActivity.join_time < end_date)
                       .scalar() or 0)
        total_joins = (VoiceActivity.select()
                       .where(VoiceActivity.user == user_db,
                              VoiceActivity.join_time >= start_date,
                              VoiceActivity.join_time < end_date).count())
        game_nights_attended = db_manager.get_attended_game_nights_count(user_db.id, start_date, end_date)
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Discord Wrapped {target_year}", color=discord.Color.purple()
        )
        embed.add_field(name="Total Time in Voice", value=f"{total_hours} hours", inline=False)
        embed.add_field(name="Days Joined Voice", value=f"{unique_days} days", inline=False)
        embed.add_field(name="Total Joins", value=f"{total_joins} times", inline=False)
        embed.add_field(name="Game Nights Attended", value=f"{game_nights_attended} nights", inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="game_night_history", description="Shows a user's past game night attendance.")
    @app_commands.describe(user="The user whose game night history you want to view. Defaults to yourself.")
    async def game_night_history(self, interaction: discord.Interaction, user: discord.Member = None):
        """Show a user's game night attendance history."""
        await interaction.response.defer()
        target_user = user or interaction.user
        user_db = db_manager.get_user_by_discord_id(str(target_user.id))
        if not user_db:
            raise UserNotFoundError(f"{target_user.display_name} has no recorded game night history.")
        game_nights = db_manager.get_user_game_night_history(user_db.id)
        embed = discord.Embed(title=f"{target_user.display_name}'s Game Night History", color=discord.Color.green())
        if not game_nights:
            embed.description = "No game nights attended yet."
        else:
            lines = [
                f"**{gn.scheduled_time:%Y-%m-%d %I:%M %p}**: "
                f"{gn.selected_game.name if gn.selected_game else '(Game not selected)'}"
                for gn in game_nights
            ]
            embed.description = "\n".join(lines[:10])
            if len(lines) > 10:
                embed.set_footer(text=f"Showing 10 of {len(lines)} attended game nights.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="set_main_channel", description="Sets the main channel for polls and announcements.")
    @app_commands.describe(channel="The channel to set as the main channel.")
    @app_commands.default_permissions(manage_guild=True)
    async def set_main_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the guild's main channel for announcements."""
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return
        db_manager.set_guild_main_channel(str(interaction.guild.id), str(channel.id))
        await interaction.followup.send(f"Main channel has been set to {channel.mention}.")

async def setup(bot):
    """Load the UtilityCommands cog."""
    await bot.add_cog(UtilityCommands(bot))
