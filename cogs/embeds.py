import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
import json
import config
from services.icai_scraper import fetch_todays_announcements
import os

ANNOUNCEMENT_CHANNEL_ID = int(os.getenv("ANNOUNCEMENT_CHANNEL_ID", "0"))


def load_state():
    with open(config.STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


class Embeds(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.icai_check.is_running():
            self.icai_check.start()
            print("[CSSBot] Embeds & ICAI automation loaded")

    # ---------- MANUAL ANNOUNCE (WITH IMAGE) ----------

    @app_commands.command(name="announce", description="Post a clean embedded announcement")
    async def announce(
        self,
        interaction: discord.Interaction,
        title: str,
        message: str,
        link: str = None,
        image: discord.Attachment = None
    ):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "You don’t have permission to use this command.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=title,
            description=message,
            color=0x2B6CB0,
            timestamp=datetime.utcnow()
        )

        if link:
            embed.url = link

        if image:
            embed.set_image(url=image.url)

        embed.set_footer(text="CA Study Space")

        await interaction.response.send_message(embed=embed)
    
    # ---------- ICAI AUTOMATION ----------
    @tasks.loop(minutes=120)
    async def icai_check(self):
        print("[CSSBot] ICAI Checking for new announcements...")
        if ANNOUNCEMENT_CHANNEL_ID == 0:
            return

        channel = self.bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not channel:
            return

        state = load_state()
        posted = set(state.get("posted_announcements", []))

        announcements = fetch_todays_announcements()

        for ann in announcements:
            if ann["id"] in posted:
                continue

            embed = discord.Embed(
                title="ICAI Examination Announcement",
                description=f"**{ann['title']}**",
                url=ann["url"],
                color=0x2B6CB0,
                timestamp=datetime.utcnow()
            )

            embed.add_field(name="Date", value=ann["date"], inline=False)
            embed.set_footer(text="Source: ICAI BOS Portal")

            await channel.send(embed=embed)

            posted.add(ann["id"])

        state["posted_announcements"] = list(posted)
        save_state(state)

    @icai_check.before_loop
    async def before_icai_check(self):
        print("[CSSBot] ICAI Waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        print("[CSSBot] ICAI Bot ready, starting task")

    @commands.Cog.listener()
    async def on_ready(self):
        print("[CSSBot] Embeds & ICAI automation loaded")

        if not self.icai_check.is_running():
            self.icai_check.start()
            print("[CSSBot] ICAI check task started")


async def setup(bot):
    await bot.add_cog(Embeds(bot))