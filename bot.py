import discord
from discord.ext import commands
import asyncio
import config

from services.utils import ensure_state_file, ensure_tickets_file
from cogs.tickets import TicketEntryView, TranscriptActionView

# -----------------------
# Intents
# -----------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.reactions = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# -----------------------
# Events
# -----------------------
@bot.event
async def on_ready():
    print(f"[CSSBot] Logged in as {bot.user}")

    # Register persistent views
    bot.add_view(TicketEntryView())
    bot.add_view(TranscriptActionView("DUMMY"))

    await ensure_ticket_entry_message(bot)

# -----------------------
# Ensure entry message
# -----------------------
async def ensure_ticket_entry_message(bot):
    channel = bot.get_channel(config.STUDY_GROUP_REQUEST_CHANNEL_ID)
    if not channel:
        print("[CSSBot] study-group-request channel not found")
        return

    async for msg in channel.history(limit=25):
        if msg.author == bot.user and msg.components:
            return  # Entry message already exists

    embed = discord.Embed(
        title="📘 Study Group Requests",
        description=(
            "Click the button below to open a study group ticket!\n\n"
            "- Select the exact number of members\n"
            "- Include yourself in the group\n"
            "- All fields must be filled"
        ),
        color=0x2B6CB0
    )

    await channel.send(
        embed=embed,
        view=TicketEntryView()
    )

    print("[CSSBot] Entry button posted")

# -----------------------
# Load cogs
# -----------------------
@bot.event
async def setup_hook():
    await bot.load_extension("cogs.embeds")
    await bot.load_extension("cogs.tickets")

# -----------------------
# Boot
# -----------------------
if __name__ == "__main__":
    ensure_state_file()
    ensure_tickets_file()
    bot.run(config.DISCORD_TOKEN)