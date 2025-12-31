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
# Image Attachment View
# -----------------------
class ImageAttachmentView(discord.ui.View):
    def __init__(self, embed, message):
        super().__init__(timeout=180)
        self.embed = embed
        self.message = message
        self.interaction_user = None

    @discord.ui.button(
        label="Attach Image",
        style=discord.ButtonStyle.primary,
        emoji="🖼️"
    )
    async def attach_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.interaction_user = interaction.user
        await interaction.response.send_message(
            "📎 **Upload your image now** (you have 2 minutes)\n"
            "Send the image as a message in this channel.",
            ephemeral=True
        )

        # Wait for image upload
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

            attachment = image_msg.attachments[0]
            
            # Check if it's an image
            if not attachment.content_type or not attachment.content_type.startswith('image/'):
                await interaction.followup.send(
                    "❌ Please upload an image file (PNG, JPG, GIF, etc.)",
                    ephemeral=True
                )
                return

            self.embed.set_image(url=attachment.url)
            await self.message.edit(embed=self.embed, view=None)
            
            # Delete the user's image message for cleanliness
            try:
                await image_msg.delete()
            except:
                pass

            await interaction.followup.send(
                "✅ Image attached successfully!",
                ephemeral=True
            )

            # Disable all buttons after successful attachment
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)

        except TimeoutError:
            await interaction.followup.send(
                "⏱️ Timeout! Image was not attached.",
                ephemeral=True
            )

    @discord.ui.button(
        label="Skip Image",
        style=discord.ButtonStyle.secondary,
        emoji="➡️"
    )
    async def skip_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "✅ Announcement posted without image.",
            ephemeral=True
        )
        # Remove the view
        await self.message.edit(view=None)
        self.stop()

    async def on_timeout(self):
        # Clean up buttons after timeout
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


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

    ann_color = discord.ui.TextInput(
        label="Color (optional)",
        placeholder="Hex color code (e.g., 2B6CB0) or leave empty for default blue",
        max_length=6,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Parse color
        color = 0x2B6CB0  # Default blue
        if self.ann_color.value:
            try:
                color = int(self.ann_color.value.replace('#', ''), 16)
            except ValueError:
                color = 0x2B6CB0

        embed = discord.Embed(
            title=self.ann_title.value,
            description=self.ann_body.value,
            color=color,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="CA Study Space")

        # Send the announcement with image attachment buttons
        msg = await interaction.channel.send(
            embed=embed,
            view=ImageAttachmentView(embed, None)
        )

        # Update the view with the actual message reference
        view = ImageAttachmentView(embed, msg)
        await msg.edit(view=view)

        await interaction.response.send_message(
            "✅ Announcement posted! Use the buttons below the announcement to attach an image if needed.",
            ephemeral=True
        )


# -----------------------
# Alternative: Slash Command with Image Parameter
# -----------------------
class AnnounceWithImageModal(discord.ui.Modal, title="Announcement with Image"):
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

    ann_color = discord.ui.TextInput(
        label="Color (optional)",
        placeholder="Hex color code (e.g., 2B6CB0)",
        max_length=6,
        required=False
    )

    image_url = discord.ui.TextInput(
        label="Image URL (optional)",
        placeholder="https://example.com/image.png",
        max_length=500,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Parse color
        color = 0x2B6CB0
        if self.ann_color.value:
            try:
                color = int(self.ann_color.value.replace('#', ''), 16)
            except ValueError:
                color = 0x2B6CB0

        embed = discord.Embed(
            title=self.ann_title.value,
            description=self.ann_body.value,
            color=color,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="CA Study Space")

        # Add image if URL provided
        if self.image_url.value:
            embed.set_image(url=self.image_url.value)

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message(
            "✅ Announcement posted successfully!",
            ephemeral=True
        )


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

    # ---------- ANNOUNCE (with button-based image attachment) ----------
    @app_commands.command(
        name="announce",
        description="Post a formatted announcement with optional image"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def announce(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AnnounceModal())

    # ---------- ANNOUNCE WITH URL (alternative method) ----------
    @app_commands.command(
        name="announce_url",
        description="Post announcement with image URL directly"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def announce_url(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AnnounceWithImageModal())

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