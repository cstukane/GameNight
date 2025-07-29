from datetime import datetime

import discord
from discord.ext import commands, tasks

from data import db_manager  # Import db_manager
from data.database import db
from data.models import User, VoiceActivity
from utils.logging import logger


class VoiceActivityCog(commands.Cog):
    """A cog for tracking user voice activity."""

    def __init__(self, bot):
        """Initialize the VoiceActivityCog."""
        self.bot = bot
        self.voice_activity_buffer = [] # Buffer for voice activity records
        self.save_voice_activity_to_db.start()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Track when users join and leave voice channels."""
        # Ignore bots to prevent them from triggering notifications
        if member.bot:
            return

        logger.info(f"Voice state update detected for {member.display_name}")

        # Check if user joined a new channel (they weren't in one before)
        if before.channel is None and after.channel is not None:
            log_msg = (
                f"{member.display_name} joined voice channel {after.channel.name} "
                f"in {after.channel.guild.name}"
            )
            logger.info(log_msg)

            # --- DATABASE BUFFERING FOR JOIN (for your stats) ---
            self.voice_activity_buffer.append({
                "user_id": str(member.id),
                "username": member.display_name,
                "guild_id": str(member.guild.id),
                "channel_id": str(after.channel.id),
                "join_time": datetime.now(),
                "type": "join"
            })

            # --- NEW, SIMPLIFIED NOTIFICATION LOGIC ---
            # Only send a notification if the user is the FIRST one in the channel.
            if len(after.channel.members) == 1:
                try:
                    # 1. Get the guild's configuration from the database.
                    guild_config = db_manager.get_guild_config(str(member.guild.id))
                    if not (guild_config and guild_config.voice_notification_channel_id):
                        logger.info(f"No voice notification channel set for guild {member.guild.name}. Skipping notification.")
                        return

                    target_channel = self.bot.get_channel(int(guild_config.voice_notification_channel_id))
                    if not target_channel:
                        logger.warning(f"Could not find the configured notification channel with ID {guild_config.voice_notification_channel_id}.")
                        return

                    # 2. Create and send a simple message. No pings needed!
                    notification_message = (
                        f"**{member.display_name}** has started a party in the **{after.channel.name}** voice channel. Come join the fun!"
                    )
                    await target_channel.send(notification_message)
                    logger.info(f"Sent voice join announcement to #{target_channel.name}.")

                except discord.Forbidden:
                    # This error means the bot doesn't have permission to talk in the target channel.
                    log_msg = f"Missing permissions to send messages in the configured notification channel."
                    logger.warning(log_msg)
                except Exception as e:
                    logger.error(f"An unexpected error occurred while sending voice join notification: {e}", exc_info=True)


        # User left a voice channel
        elif before.channel is not None and after.channel is None:
            log_msg = (
                f"{member.display_name} left voice channel {before.channel.name} "
                f"in {before.channel.guild.name}"
            )
            logger.info(log_msg)

            # Add leave event to the buffer
            self.voice_activity_buffer.append({
                "user_id": str(member.id),
                "username": member.display_name,
                "guild_id": str(member.guild.id),
                "channel_id": str(before.channel.id),
                "leave_time": datetime.now(),
                "type": "leave"
            })

    @tasks.loop(minutes=5)
    async def save_voice_activity_to_db(self):
        """Periodically saves buffered voice activity records to the database."""
        if not self.voice_activity_buffer:
            return

        logger.info(f"Saving {len(self.voice_activity_buffer)} voice activity records to DB...")
        with db.atomic():
            records_to_process = list(self.voice_activity_buffer)
            self.voice_activity_buffer.clear()

            for record in records_to_process:
                try:
                    # Make sure user exists in DB before creating activity records
                    user, created = User.get_or_create(
                        discord_id=record["user_id"], defaults={'username': record["username"]}
                    )
                    if created:
                        logger.info(f"Created new user entry for {record['username']} during voice activity save.")

                    if record["type"] == "join":
                        VoiceActivity.create(
                            user=user,
                            guild_id=record["guild_id"],
                            channel_id=record["channel_id"],
                            join_time=record["join_time"]
                        )
                    elif record["type"] == "leave":
                        latest_activity = VoiceActivity.select().where(
                            VoiceActivity.user == user,
                            VoiceActivity.guild_id == record["guild_id"],
                            VoiceActivity.channel_id == record["channel_id"],
                            VoiceActivity.leave_time.is_null()
                        ).order_by(VoiceActivity.join_time.desc()).first()

                        if latest_activity:
                            latest_activity.leave_time = record["leave_time"]
                            latest_activity.duration_seconds = (latest_activity.leave_time - latest_activity.join_time).total_seconds()
                            latest_activity.save()
                except Exception as e:
                    logger.error(f"Error processing voice activity record {record}: {e}", exc_info=True)

    @save_voice_activity_to_db.before_loop
    async def before_save_voice_activity_to_db(self):
        await self.bot.wait_until_ready()
        logger.info("Waiting for bot to be ready before starting voice activity save loop.")

    @save_voice_activity_to_db.after_loop
    async def after_save_voice_activity_to_db(self):
        if self.voice_activity_buffer:
            logger.info("Voice activity save loop stopped. Saving remaining records...")
            # Run the save task one last time without awaiting the loop
            self.save_voice_activity_to_db.coro(self)


async def setup(bot):
    """Set up the cog and add it to the bot."""
    await bot.add_cog(VoiceActivityCog(bot))
