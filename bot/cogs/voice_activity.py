from datetime import datetime

import discord
from discord.ext import commands

from data.database import db
from data.models import User, VoiceActivity
from utils.logging import logger


class VoiceActivityCog(commands.Cog):
    """A cog for tracking user voice activity."""

    def __init__(self, bot):
        """Initialize the VoiceActivityCog."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Track when users join and leave voice channels."""
        # User joined a voice channel
        if before.channel is None and after.channel is not None:
            log_msg = (
                f"{member.display_name} joined voice channel {after.channel.name} "
                f"in {after.channel.guild.name}"
            )
            logger.info(log_msg)

            # Store voice activity in the database
            try:
                with db.atomic():
                    user, _ = User.get_or_create(
                        discord_id=str(member.id), defaults={'username': member.display_name}
                    )
                    VoiceActivity.create(
                        user=user,
                        guild_id=str(member.guild.id),
                        channel_id=str(after.channel.id),
                        join_time=datetime.now()
                    )
            except Exception as e:
                logger.error(f"Error saving voice activity for {member.display_name}: {e}")

            # Send notification to a designated text channel
            if after.channel.guild.system_channel:
                try:
                    await after.channel.guild.system_channel.send(
                        f"**{member.display_name}** has joined **{after.channel.name}**! Come join the fun!"
                    )
                except discord.Forbidden:
                    log_msg = f"Missing permissions to send messages in {after.channel.guild.system_channel.name}"
                    logger.warning(log_msg)
                except Exception as e:
                    logger.error(f"Error sending voice join notification: {e}")

        # User left a voice channel
        elif before.channel is not None and after.channel is None:
            log_msg = (
                f"{member.display_name} left voice channel {before.channel.name} "
                f"in {before.channel.guild.name}"
            )
            logger.info(log_msg)

            # Update the leave time for the last voice activity record
            try:
                with db.atomic():
                    user = User.get_or_none(discord_id=str(member.id))
                    if user:
                        # Find the most recent un-ended voice activity for this user
                        latest_activity = VoiceActivity.select().where(
                            VoiceActivity.user == user,
                            VoiceActivity.guild_id == str(member.guild.id),
                            VoiceActivity.channel_id == str(before.channel.id),
                            VoiceActivity.leave_time.is_null()
                        ).order_by(VoiceActivity.join_time.desc()).first()

                        if latest_activity:
                            latest_activity.leave_time = datetime.now()
                            latest_activity.save()
            except Exception as e:
                logger.error(f"Error updating voice activity for {member.display_name}: {e}")


async def setup(bot):
    """Set up the cog and add it to the bot."""
    await bot.add_cog(VoiceActivityCog(bot))
