import discord
from discord.ext import commands
import asyncio
import config

from services.utils import ensure_state_file
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

    # Sync commands
    synced = await bot.tree.sync()
    print(f"[CSSBot] Synced {len(synced)} commands")

    # Register persistent views
    bot.add_view(TicketEntryView())
    bot.add_view(TranscriptActionView("DUMMY"))

    await ensure_ticket_entry_message(bot)

    # Ensure welcome and rules embeds are posted
    await ensure_embed_posted_once(
        bot,
        config.WELCOME_CHANNEL_ID,
        get_welcome_embed()
    )

    await ensure_embed_posted_once(
        bot,
        config.RULES_CHANNEL_ID,
        get_rules_embed()
    )

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

# ------------------------------------------
# Ensure welcome and rules embed posted once
# ------------------------------------------

async def ensure_embed_posted_once(
    bot: commands.Bot,
    channel_id: int,
    embed: discord.Embed
):
    channel = bot.get_channel(channel_id)
    if not channel:
        print(f"[CSSBot] Channel {channel_id} not found")
        return

    async for msg in channel.history(limit=25):
        if (
            msg.author == bot.user
            and msg.embeds
            and msg.embeds[0].title == embed.title
        ):
            return  # Message already exists

    await channel.send(embed=embed)
    print(f"[CSSBot] Posted: {embed.title}")

def get_welcome_embed():
    return discord.Embed(
        title="👋 Welcome to CA Study Space",
        description=(
            "This is an unofficial, invite-only study space for CA students.\n"
            "The goal is simple: **clear thinking, disciplined discussion, and shared effort.**\n\n"

            "This server is **not a replacement** for classes or self-study.\n"
            "It exists to ask precise doubts, discuss concepts, and learn from each other’s mistakes.\n\n"

            "Please take a moment to read the **rules-and-culture** channel.\n\n"

            "Keep your doubts sharp, your discussions respectful,\n"
            "and your chai strong."
        ),
        color=0x2B6CB0
    )

def get_rules_embed():
    return discord.Embed(
        title="📜 Rules & Culture",
        description=(
            "**1. Ask precise doubts**\n"
            "One concept at a time. Show what you’ve tried. Panic posts help no one.\n\n"

            "**2. Use the forum properly**\n"
            "Conceptual and subject-level doubts go in the forum. Quick clarifications go in the quick-clarification channel.\n\n"

            "**3. No shortcuts, no selling**\n"
            "No course promotion, piracy, or exam hacks. We do the work properly here.\n\n"

            "**4. Respect time and effort**\n"
            "Help when you can. Disagree calmly. Correct without condescension.\n\n"

            "**5. Keep it academic**\n"
            "No politics, drama, or negativity spirals. Chill chats stay in the chai-break channel.\n\n"

            "**6. Notes are guidance, not substitutes**\n"
            "Shared resources support study — they don’t replace it.\n\n"

            "**7. Quiet but firm moderation**\n"
            "Repeated noise or misinformation may lead to removal.\n\n"

            "This space is meant to be calm, focused, and supportive.\n"
            "We already have enough panic in our CA journey — let’s not add to it."
        ),
        color=0x805AD5
    )

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
    bot.run(config.DISCORD_TOKEN)