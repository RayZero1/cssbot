import os
from dotenv import load_dotenv

load_dotenv()

# --- Core Discord Config ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Optional: restrict to one server later
GUILD_ID = os.getenv("GUILD_ID")  # string, cast later if used

# Variables for ticketing system
STUDY_GROUP_REQUEST_CHANNEL_ID = int(os.getenv("STUDY_GROUP_REQUEST_CHANNEL_ID"))
TRANSCRIPTS_CHANNEL_ID = int(os.getenv("TRANSCRIPTS_CHANNEL_ID"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))
STUDY_ROOM_CATEGORY_NAME = "Study Rooms"
TICKETS_CATAGORY_NAME = "Tickets"

# Variables for welcome and rules embeds
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID"))
RULES_CHANNEL_ID = int(os.getenv("RULES_CHANNEL_ID"))
ICAI_ANNOUNCEMENT_CHANNEL_ID = int(os.getenv("ANNOUNCEMENT_CHANNEL_ID"))

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

# --- Bot Behaviour ---
BOT_NAME = "CSSBot"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")