import discord
from discord.ext import commands
import json
from datetime import datetime
import config

DATA_FILE = "data/tickets.json"

# =================================================
# Data helpers
# =================================================

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def next_ticket_id(data):
    data["last_ticket_id"] += 1
    return f"{data['last_ticket_id']:02d}"

# =================================================
# Transcript helpers
# =================================================

async def post_transcript(bot, ticket_id, ticket):
    channel = bot.get_channel(config.TRANSCRIPTS_CHANNEL_ID)
    if not channel:
        return None

    embed = discord.Embed(
        title=f"🎫 Study Group Ticket #{ticket_id}",
        color=0x5865F2,
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="Group Name", value=ticket["group_name"], inline=False)
    embed.add_field(name="Level", value=ticket["level"], inline=True)
    embed.add_field(name="Members Required", value=ticket["member_count"], inline=True)
    embed.add_field(
        name="Members",
        value=" ".join(f"<@{u}>" for u in ticket["members"]),
        inline=False
    )
    embed.add_field(name="Status", value="🟢 OPEN", inline=True)

    msg = await channel.send(
        embed=embed,
        view=TranscriptActionView(ticket_id)
    )
    return msg.id


async def update_transcript(bot, ticket_id, ticket, status_text):
    channel = bot.get_channel(config.TRANSCRIPTS_CHANNEL_ID)
    if not channel:
        return

    try:
        msg = await channel.fetch_message(ticket["transcript_message_id"])
    except discord.NotFound:
        return

    embed = msg.embeds[0]
    embed.clear_fields()

    embed.add_field(name="Group Name", value=ticket["group_name"], inline=False)
    embed.add_field(name="Level", value=ticket["level"], inline=True)
    embed.add_field(name="Members Required", value=ticket["member_count"], inline=True)
    embed.add_field(
        name="Members",
        value=" ".join(f"<@{u}>" for u in ticket["members"]),
        inline=False
    )
    embed.add_field(name="Status", value=status_text, inline=True)

    await msg.edit(embed=embed, view=None)

# =================================================
# Channel + consent creation
# =================================================

async def create_ticket_channel(guild, ticket_id, ticket, admin):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False)
    }

    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    overwrites[admin] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    for uid in ticket["members"]:
        member = guild.get_member(uid)
        if not member:
            try:
                member = await guild.fetch_member(uid)
            except discord.NotFound:
                continue

        overwrites[member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True
        )

    channel = await guild.create_text_channel(
        name=f"ticket-{ticket_id}",
        overwrites=overwrites,
        category=discord.utils.get(
            guild.categories,
            name=config.TICKETS_CATAGORY_NAME
        ),
        reason=f"Study group ticket {ticket_id}"
    )

    consent = await channel.send(
        "🔔 **Consent Required**\n\n"
        "All listed members must react with ✅ to confirm participation:\n\n"
        + " ".join(f"<@{u}>" for u in ticket["members"])
    )
    await consent.add_reaction("✅")

    return channel, consent.id

# =================================================
# Transcript action (Claim)
# =================================================

class TranscriptActionView(discord.ui.View):
    def __init__(self, ticket_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.primary,
        emoji="🛠️",
        custom_id="cssbot_claim_ticket"
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Admins only.", ephemeral=True)
            return

        data = load_data()
        ticket = data["tickets"].get(self.ticket_id)

        if not ticket or ticket["status"] != "OPEN":
            await interaction.followup.send("⚠️ Ticket unavailable.", ephemeral=True)
            return

        ticket["status"] = "CLAIMED"
        ticket["claimed_by"] = interaction.user.id

        channel, approval_msg_id = await create_ticket_channel(
            interaction.guild, self.ticket_id, ticket, interaction.user
        )

        ticket["approval_message_id"] = approval_msg_id
        ticket["approved_members"] = []

        save_data(data)

        await update_transcript(
            interaction.client,
            self.ticket_id,
            ticket,
            f"🟡 CLAIMED by <@{interaction.user.id}>"
        )

        await interaction.followup.send(
            f"✅ Ticket claimed. Channel created: {channel.mention}",
            ephemeral=True
        )

# =================================================
# Cog + reaction approval
# =================================================

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name != "✅":
            return
        if payload.user_id == self.bot.user.id:
            return

        data = load_data()

        for ticket_id, ticket in data["tickets"].items():
            if ticket.get("approval_message_id") != payload.message_id:
                continue

            if payload.user_id not in ticket["members"]:
                return
            if payload.user_id in ticket["approved_members"]:
                return

            ticket["approved_members"].append(payload.user_id)
            save_data(data)

            if set(ticket["approved_members"]) == set(ticket["members"]):
                await self.finalize_ticket(payload.guild_id, ticket_id)

            return

    async def finalize_ticket(self, guild_id, ticket_id):
        data = load_data()
        ticket = data["tickets"].get(ticket_id)
        if not ticket:
            return

        ticket["status"] = "APPROVED"
        ticket["approved_members"] = []
        ticket["approval_message_id"] = None

        await update_transcript(
            self.bot,
            ticket_id,
            ticket,
            "🟢 APPROVED"
        )

        guild = self.bot.get_guild(guild_id)
        if guild:
            channel = discord.utils.get(guild.text_channels, name=f"ticket-{ticket_id}")
            if channel:
                await channel.delete(reason="Study group approved")

        # Create role and voice channel
        role = await create_study_role(guild, ticket)

        # Assign role to members
        await assign_role_to_members(guild, role, ticket["members"])

        # Create private voice channel
        await create_private_voice_channel(guild, role, ticket)

        save_data(data)

# =================================================
# Role and voice channel creation
# =================================================

async def create_study_role(guild, ticket):
    role_name = f"SG_{ticket['group_name']}"

    # Avoid duplicate roles
    existing = discord.utils.get(guild.roles, name=role_name)
    if existing:
        return existing

    role = await guild.create_role(
        name=role_name,
        mentionable=False,
        reason=f"Study group approved ({ticket['group_name']})"
    )
    return role


async def assign_role_to_members(guild, role, member_ids):
    for uid in member_ids:
        member = guild.get_member(uid)
        if not member:
            try:
                member = await guild.fetch_member(uid)
            except discord.NotFound:
                continue

        await member.add_roles(
            role,
            reason="Study group approved"
        )


async def create_private_voice_channel(guild, role, ticket):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True
        )
    }

    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True
        )

    channel = await guild.create_voice_channel(
        name=f"SG_{ticket['group_name']}",
        overwrites=overwrites,
        category=discord.utils.get(
            guild.categories,
            name=config.STUDY_ROOM_CATEGORY_NAME
        ),
        reason="Study group approved"
    )
    return channel

# =================================================
# Ticket creation UI
# =================================================

class StudyGroupModal(discord.ui.Modal, title="Study Group Details"):
    group_name = discord.ui.TextInput(label="Study Group Name", max_length=50)

    def __init__(self, creator):
        super().__init__()
        self.creator = creator

    async def on_submit(self, interaction):
        view = StudyGroupFormView(self.creator, self.group_name.value)
        await interaction.response.send_message(
            embed=view.embed,
            view=view,
            ephemeral=True
        )


class StudyGroupFormView(discord.ui.View):
    def __init__(self, creator, group_name):
        super().__init__(timeout=300)
        self.creator = creator
        self.group_name = group_name
        self.member_count = None
        self.level = None
        self.members = []

        self.embed = discord.Embed(
            title="Study Group Request",
            description=f"**Group Name:** {group_name}",
            color=0x2B6CB0
        )
        self.update_embed()

        self.add_item(MemberCountSelect())
        self.add_item(LevelSelect())
        self.add_item(MemberUserSelect())

    def update_embed(self):
        self.embed.clear_fields()
        self.embed.add_field(
            name="Members Required",
            value=str(self.member_count) if self.member_count else "—",
            inline=True
        )
        self.embed.add_field(
            name="Level",
            value=self.level if self.level else "—",
            inline=True
        )
        self.embed.add_field(
            name="Members Selected",
            value=str(len(self.members)),
            inline=True
        )

    def valid(self):
        return (
            self.member_count
            and self.level
            and len(self.members) == self.member_count
            and self.creator.id in self.members
        )

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.success)
    async def submit(self, interaction, button):
        if not self.valid():
            await interaction.response.send_message("❌ Invalid submission.", ephemeral=True)
            return

        data = load_data()
        tid = next_ticket_id(data)

        ticket = {
            "group_name": self.group_name,
            "level": self.level,
            "member_count": self.member_count,
            "members": self.members,
            "created_by": self.creator.id,
            "status": "OPEN",
            "claimed_by": None,
            "approval_message_id": None,
            "approved_members": [],
            "transcript_message_id": None
        }

        ticket["transcript_message_id"] = await post_transcript(
            interaction.client, tid, ticket
        )

        data["tickets"][tid] = ticket
        save_data(data)

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Ticket Created",
                description=f"Ticket **#{tid}** created successfully.",
                color=0x2ECC71
            ),
            view=None
        )

# =================================================
# Select menus (3–5 enforced)
# =================================================

class MemberCountSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Members (2–5)",
            options=[
                discord.SelectOption(label="2", value="2"),
                discord.SelectOption(label="3", value="3"),
                discord.SelectOption(label="4", value="4"),
                discord.SelectOption(label="5", value="5"),
            ]
        )

    async def callback(self, interaction):
        self.view.member_count = int(self.values[0])
        self.view.update_embed()
        await interaction.response.edit_message(embed=self.view.embed, view=self.view)


class LevelSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Level",
            options=[
                discord.SelectOption(label="CA Final", value="Final"),
                discord.SelectOption(label="CA Inter", value="Inter"),
                discord.SelectOption(label="Foundation", value="Foundation"),
            ]
        )

    async def callback(self, interaction):
        self.view.level = self.values[0]
        self.view.update_embed()
        await interaction.response.edit_message(embed=self.view.embed, view=self.view)


class MemberUserSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Select members (include yourself)", min_values=2, max_values=5)

    async def callback(self, interaction):
        self.view.members = [u.id for u in self.values]
        self.view.update_embed()
        await interaction.response.edit_message(embed=self.view.embed, view=self.view)

# =================================================
# Entry button
# =================================================

class TicketEntryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open a ticket!",
        emoji="📘",
        style=discord.ButtonStyle.primary,
        custom_id="cssbot_open_ticket"
    )
    async def open_ticket(self, interaction, button):
        await interaction.response.send_modal(
            StudyGroupModal(interaction.user)
        )

# =================================================
# Setup
# =================================================

async def setup(bot):
    await bot.add_cog(Tickets(bot))