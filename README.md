# CSSBot — CA Study Space Bot

CSSBot is a custom Discord bot built for **CA students** to manage structured study groups with **zero noise and zero panic**.

It combines moderation workflows, study group automation, announcement embeds, and ICAI exam updates into one calm, purpose-built system.

---

## ✨ Features

### 🎫 Study Group Ticket System
- Modal-based ticket creation
- Member selection & validation
- Admin claim workflow
- Private ticket channels
- Reaction-based consent system
- Automatic approval

---

### 📜 Transcript Logging
- One immutable transcript per ticket
- Full audit trail:
  - OPEN → CLAIMED → APPROVED
- Stored in a dedicated transcripts channel

---

### ✅ Consent-Based Approval
- All selected members must explicitly approve
- Uses reaction-based confirmation (✅)
- Fully automatic — no admin babysitting

---

### 🎭 Automatic Study Roles
- Unique role created per approved study group
- Assigned automatically to all approved members
- Used as the single source of permissions

---

### 🔊 Private Voice Study Rooms
- Created automatically on approval
- Placed under **Study Rooms** category
- Accessible only to the study group role + admins

---

### 📢 Embed Announcement System
- Admins can send clean, formatted announcements
- Uses an `announce` command to post embeds
- Useful for:
  - exam tips
  - deadlines
  - internal updates
- Replaces the need for separate embed bots

---

### 🏛️ ICAI Automated Announcements
- Periodically checks ICAI BOS portal for new announcements
- Automatically posts updates to a designated channel
- Built with fail-safes:
  - network timeouts handled gracefully
  - no bot crashes if ICAI site is down
- Silent when no updates exist

---

### 🧹 Clean & Calm UX
- Ticket channels auto-delete after approval
- No spam pings
- No unnecessary notifications
- Designed to **reduce anxiety**, not amplify it

---

## 🏗️ Project Structure

```markdown
CSSBOT/
├── bot.py
├── config.py
├── .env
├── requirements.txt
├── README.md
│
├── cogs/
│   ├── __init__.py
│   ├── embeds.py
│   └── tickets.py
│
├── services/
│   ├── __init__.py
│   ├── database.py
│   ├── icai_scraper.py
│   └── utils.py
│
├── data/
│   ├── state.json
│   └── tickets.json
│
├── logs/
├── venv/
```
## ⚙️ Setup Instructions

### 1️⃣ Clone the repository

```bash
git clone https://github.com/RayZero1/cssbot
cd cssbot
```

### 2️⃣ Create and activate virtual environment

```bash
python -m venv venv
venv\Scripts\activate   # Windows
```

### 3️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Create config.py
Create a file named config.py with the following content:

```python
DISCORD_TOKEN = "YOUR_BOT_TOKEN"

# Channels
TRANSCRIPTS_CHANNEL_ID = 1234567890
STUDY_GROUP_REQUEST_CHANNEL_ID = 1234567890
WELCOME_CHANNEL_ID = 1234567890
RULES_CHANNEL_ID = 1234567890

# Role ID
ADMIN_ROLE_ID = 1234567890

# Categories
STUDY_ROOMS_CATEGORY_NAME = "Study Rooms"
TICKETS_CATAGORY_NAME = "Tickets"
```

### 5️⃣ Enable Discord Gateway Intents

In Discord Developer Portal → Bot → Privileged Gateway Intents:
    ✅ Server Members Intent
    ✅ Message Content Intent

After enabling:
1. Save changes
2. Invite the bot
3. Start the bot

### 6️⃣ Run the bot

```bash
python bot.py
```

### 📢 Embed Announcement Command

Admins can post clean embed announcements using the "/announce" command.

The bot will prompt for:
- Title
- Description
- Optional footer / colour (depending on configuration)

This replaces external embed bots and keeps announcements consistent.

### 🏛️ ICAI Announcement Automation

CSSBot automatically checks the ICAI BOS portal: https://boslive.icai.org/examination_announcement.php

#### How it works:

- Runs on a scheduled background task
- Detects new announcements
- Posts them as embeds in the ICAI announcement channel
- Skips silently if:
    - no new announcements
    - ICAI website is slow or unreachable

#### Fail-safe design:

- Network timeouts handled
- Exceptions logged but never crash the bot
- Bot continues running normally even if ICAI site is down

### 🔐 Required Bot Permissions

Recommended during development:
1. Administrator

Minimum required:
1. Manage Channels
2. Manage Roles
3. Read Message History
4. Add Reactions
5. Send Messages
6. Embed Links
7. View Channels

### 🧠 Design Philosophy

CSSBot is built on one principle:

"Structure should reduce stress, not create it."

- No spam.
- No panic.
- No clutter.

Just quiet systems doing their job.

### 📄 License

MIT License
Free to fork, modify, and improve.
