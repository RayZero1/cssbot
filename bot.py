import discord
from discord.ext import commands
import asyncio
import config

from services.utils import ensure_state_file
from cogs.tickets import TicketEntryView, TranscriptActionView
from services.database import init_db

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
        get_welcome_embed(),
        "assets/ca_welcome.png"
    )

    await ensure_embed_posted_once(
        bot,
        config.RULES_CHANNEL_ID,
        get_rules_embed(),
        "assets/ca_rules.png"
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
    embed: discord.Embed,
    image_path: str = None
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

    # Prepare file if image path is provided
    file = None
    if image_path:
        try:
            file = discord.File(image_path, filename=image_path.split('/')[-1])
            embed.set_image(url=f"attachment://{image_path.split('/')[-1]}")
        except FileNotFoundError:
            print(f"[CSSBot] Warning: Image not found at {image_path}")

    if file:
        await channel.send(embed=embed, file=file)
    else:
        await channel.send(embed=embed)
    
    print(f"[CSSBot] Posted: {embed.title}")

def get_welcome_embed():
    return discord.Embed(
        title="👋 Welcome to CA Study Space",
        description=(
            "Welcome to **CA Study Space** — an unofficial, invite-only community built for CA students who value "
            "**clarity over chaos, and progress over panic.**\n\n"

            "This isn't a substitute for your coaching classes or self-study. "
            "It's a space to **ask sharp questions, discuss complex concepts, and learn from each other's journey** through one of India's toughest professional courses.\n\n"

            "### What We're About\n"
            "- 📚 Solving precise doubts — one concept at a time\n"
            "- 🤝 Collaborative study groups with structured workflows\n"
            "- 💬 Respectful discussions that challenge ideas, not people\n"
            "- ☕ A culture that values focus, discipline, and the occasional chai break\n\n"

            "### Before You Start\n"
            "Please read the <#1453101004244385945> channel carefully. "
            "It's short, to the point, and explains how we maintain the quality of this space.\n\n"

            "We already carry enough stress in our CA journey. "
            "This server exists to reduce it — not add to it.\n\n"

            "**Keep your doubts sharp, your discussions respectful, and your chai strong.** ☕"
        ),
        color=0x2B6CB0
    )

def get_rules_embed():
    return discord.Embed(
        title="📜 Rules & Culture",
        description=(
            "This server thrives on **structure, respect, and shared accountability.** "
            "These rules exist to protect the quality of discussion and keep the space productive.\n\n"

            "### Core Rules\n\n"

            "**1. Ask Precise Doubts**\n"
            "State one concept at a time. Show what you've already tried. Panic posts and vague questions waste everyone's time — including yours.\n\n"

            "**2. Use Channels Properly**\n"
            "- **Forum threads:** Subject-level or conceptual doubts\n"
            "- **Quick-clarification:** Short questions that need fast answers\n"
            "- **Study groups:** Use the ticket system for structured collaboration\n\n"

            "**3. No Shortcuts, No Selling**\n"
            "No course promotions. No piracy. No exam hacks or unethical workarounds. We do the work properly here.\n\n"

            "**4. Respect Time and Effort**\n"
            "Help when you can. Disagree calmly. Correct mistakes without condescension. Everyone here is learning.\n\n"

            "**5. Keep It Academic**\n"
            "No politics. No drama. No negativity spirals. Off-topic chats belong in **☕ chai-break** — nowhere else.\n\n"

            "**6. Notes Are Guidance, Not Substitutes**\n"
            "Shared resources support study — they don't replace the hard work of understanding concepts yourself.\n\n"

            "**7. Quiet But Firm Moderation**\n"
            "Admins won't micromanage, but repeated noise, misinformation, or rule violations will lead to removal.\n\n"

            "---\n\n"

            "### Culture Statement\n"
            "This space is built on one belief:\n\n"
            "> *\"Structure should reduce stress, not create it.\"*\n\n"

            "We already face enough pressure in CA. Let's not bring unnecessary chaos here.\n\n"

            "**Stay calm. Stay focused. Stay accountable.**"
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
    init_db()
    bot.run(config.DISCORD_TOKEN)