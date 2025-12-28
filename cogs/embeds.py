import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
import json
import os
import config

from services.icai_scraper import fetch_todays_announcements


# -----------------------
# State helpers
# -----------------------
STATE_FILE = "data/state.json"


def load_state():
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# -----------------------
# Announcement Modal
# -----------------------
class AnnounceModal(discord.ui.Modal, title="New Announcement"):
    ann_title = discord.ui.TextInput(
        label="Title",
        placeholder="CA Final – Important Update",
        max_length=256,
        required=True
    )

    ann_body = discord.ui.TextInput(
        label="Announcement Text",
        style=discord.TextStyle.paragraph,
        placeholder="Write your announcement here.\nNew lines are allowed.",
        max_length=2000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.ann_title.value,
            description=self.ann_body.value,
            color=0x2B6CB0,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="CA Study Space")

        msg = await interaction.channel.send(embed=embed)

        await interaction.response.send_message(
            "📎 **Optional:** Upload an image now to attach it to this announcement.\n"
            "You can ignore this message if not needed.",
            ephemeral=True
        )

        # Wait for image upload from the same user
        def check(m):
            return (
                m.author == interaction.user
                and m.channel == interaction.channel
                and m.attachments
            )

        try:
            image_msg = await interaction.client.wait_for(
                "message",
                timeout=120,
                check=check
            )
        except TimeoutError:
            return

        attachment = image_msg.attachments[0]
        embed.set_image(url=attachment.url)
        await msg.edit(embed=embed)


# -----------------------
# Embeds Cog
# -----------------------
class Embeds(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------- READY ----------
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.icai_check.is_running():
            self.icai_check.start()
            print("[CSSBot] Embeds & ICAI automation loaded")

    # ---------- ANNOUNCE ----------
    @app_commands.command(
        name="announce",
        description="Post a formatted announcement"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def announce(self, interaction: discord.Interaction):
        # No arguments, modal opens immediately
        await interaction.response.send_modal(AnnounceModal())

    # ---------- ICAI AUTOMATION ----------
    @tasks.loop(minutes=120)
    async def icai_check(self):
        channel = self.bot.get_channel(config.ICAI_ANNOUNCEMENT_CHANNEL_ID)
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
        await self.bot.wait_until_ready()


# -----------------------
# Setup
# -----------------------
async def setup(bot):
    await bot.add_cog(Embeds(bot))