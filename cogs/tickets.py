import discord
from discord.ext import commands
import json
from datetime import datetime
import io
import config
from discord import app_commands

from services.database import (
    get_ticket,
    get_all_tickets,
    save_ticket,
    next_ticket_id,
    export_tickets_json,
)

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
    return str(msg.id)


async def update_transcript(bot, ticket_id, ticket, status_text, reason=None):
    """Update transcript with status and optional reason"""
    channel = bot.get_channel(config.TRANSCRIPTS_CHANNEL_ID)
    if not channel:
        return

    try:
        msg = await channel.fetch_message(int(ticket["transcript_message_id"]))
    except (discord.NotFound, ValueError, TypeError):
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
    
    # Add cancellation reason if provided
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)

    await msg.edit(embed=embed, view=None)
    
    # Return the embed for DM use
    return embed


async def send_transcript_dm(bot, user_id, ticket_id, ticket, status_text, reason=None):
    """Send transcript to user via DM"""
    try:
        user = await bot.fetch_user(user_id)
        
        embed = discord.Embed(
            title=f"🎫 Study Group Ticket #{ticket_id} - {status_text}",
            color=0x2ECC71 if "APPROVED" in status_text else 0xE74C3C,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="Group Name", value=ticket["group_name"], inline=False)
        embed.add_field(name="Level", value=ticket["level"], inline=True)
        embed.add_field(name="Members", value=" ".join(f"<@{u}>" for u in ticket["members"]), inline=False)
        embed.add_field(name="Final Status", value=status_text, inline=True)
        
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        
        embed.set_footer(text="CA Study Space • Ticket System")
        
        await user.send(embed=embed)
        print(f"[Tickets] Sent DM to user {user_id} for ticket {ticket_id}")
        
    except discord.Forbidden:
        print(f"[Tickets] Could not DM user {user_id} - DMs disabled")
    except discord.NotFound:
        print(f"[Tickets] User {user_id} not found")
    except Exception as e:
        print(f"[Tickets] Error sending DM to {user_id}: {e}")


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

    print(f"[Tickets] Created consent message with ID: {consent.id}")
    
    return channel, str(consent.id)


# =================================================
# Cancellation Reason Modal
# =================================================

class CancellationReasonModal(discord.ui.Modal, title="Ticket Cancellation"):
    reason = discord.ui.TextInput(
        label="Reason for Cancellation",
        style=discord.TextStyle.paragraph,
        placeholder="Please provide a clear reason for cancelling this ticket...",
        required=True,
        max_length=500
    )

    def __init__(self, ticket_id, bot):
        super().__init__()
        self.ticket_id = ticket_id
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        ticket = get_ticket(self.ticket_id)
        if not ticket:
            await interaction.followup.send("⚠️ Ticket not found.", ephemeral=True)
            return

        # Update ticket with cancellation details
        ticket["status"] = "CANCELLED"
        ticket["cancelled_by"] = interaction.user.id
        ticket["cancelled_at"] = datetime.utcnow().isoformat()
        ticket["cancellation_reason"] = self.reason.value

        # Delete ticket channel if it exists
        guild = interaction.guild
        channel = discord.utils.get(guild.text_channels, name=f"ticket-{self.ticket_id}")
        if channel:
            try:
                await channel.delete(reason=f"Ticket {self.ticket_id} cancelled by admin")
            except discord.NotFound:
                pass

        # Save to database
        save_ticket(self.ticket_id, ticket)

        # Update transcript with reason
        await update_transcript(
            self.bot,
            self.ticket_id,
            ticket,
            f"🔴 CANCELLED by <@{interaction.user.id}>",
            reason=self.reason.value
        )

        # Send DM to ticket creator
        await send_transcript_dm(
            self.bot,
            ticket["created_by"],
            self.ticket_id,
            ticket,
            "CANCELLED",
            reason=self.reason.value
        )

        await interaction.followup.send(
            f"✅ Ticket #{self.ticket_id} has been cancelled.\n"
            f"**Reason:** {self.reason.value}\n\n"
            f"The ticket creator has been notified via DM.",
            ephemeral=True
        )


# =================================================
# Transcript action (Claim + Cancel)
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
        # Check permissions first (before deferring)
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        ticket = get_ticket(self.ticket_id)

        if not ticket or ticket["status"] != "OPEN":
            await interaction.response.send_message("⚠️ Ticket unavailable.", ephemeral=True)
            return

        # NOW defer (we passed all checks)
        await interaction.response.defer(ephemeral=True)

        ticket["status"] = "CLAIMED"
        ticket["claimed_by"] = interaction.user.id

        channel, approval_msg_id = await create_ticket_channel(
            interaction.guild, self.ticket_id, ticket, interaction.user
        )

        ticket["approval_message_id"] = approval_msg_id
        ticket["approved_members"] = []

        save_ticket(self.ticket_id, ticket)
        
        print(f"[Tickets] Ticket {self.ticket_id} claimed by {interaction.user.id}")

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

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="cssbot_cancel_ticket"
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        ticket = get_ticket(self.ticket_id)

        if not ticket:
            await interaction.response.send_message("⚠️ Ticket not found.", ephemeral=True)
            return

        if ticket["status"] in ["CANCELLED", "APPROVED"]:
            await interaction.response.send_message(
                f"⚠️ Cannot cancel a ticket that is already {ticket['status']}.",
                ephemeral=True
            )
            return

        # Show modal to get cancellation reason
        await interaction.response.send_modal(
            CancellationReasonModal(self.ticket_id, interaction.client)
        )

# =================================================
# Cog + reaction approval
# =================================================

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="export_tickets",
        description="Export all study group tickets as JSON for audit"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def export_tickets(self, interaction: discord.Interaction):
        json_data = export_tickets_json()

        fp = io.StringIO(json_data)
        file = discord.File(fp, filename=f"tickets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")

        await interaction.response.send_message(
            content="📊 Ticket data export:",
            file=file,
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name != "✅":
            return
        if payload.user_id == self.bot.user.id:
            return

        print(f"[Tickets] Reaction detected: User {payload.user_id} on message {payload.message_id}")

        all_tickets = get_all_tickets()
        
        print(f"[Tickets] Total tickets in DB: {len(all_tickets)}")

        for ticket_id, ticket in all_tickets.items():
            approval_msg_id = ticket.get("approval_message_id")
            
            print(f"[Tickets] Checking ticket {ticket_id}: approval_message_id = {approval_msg_id}, payload.message_id = {payload.message_id}")
            
            if str(approval_msg_id) != str(payload.message_id):
                continue

            print(f"[Tickets] Match found! Ticket {ticket_id}")

            if payload.user_id not in ticket["members"]:
                print(f"[Tickets] User {payload.user_id} not in ticket members: {ticket['members']}")
                return
            
            current_approved = ticket.get("approved_members", [])
            print(f"[Tickets] Current approved members: {current_approved}")
            
            if payload.user_id in current_approved:
                print(f"[Tickets] User {payload.user_id} already approved")
                return

            if "approved_members" not in ticket:
                ticket["approved_members"] = []
            
            ticket["approved_members"].append(payload.user_id)
            
            save_ticket(ticket_id, ticket)
            
            saved_ticket = get_ticket(ticket_id)
            print(f"[Tickets] After save - approved_members from DB: {saved_ticket.get('approved_members')}")

            if set(ticket["approved_members"]) == set(ticket["members"]):
                print(f"[Tickets] All members approved! Finalizing...")
                await self.finalize_ticket(payload.guild_id, ticket_id)
            else:
                print(f"[Tickets] Waiting for more approvals: {len(ticket['approved_members'])}/{len(ticket['members'])}")

            return
        
        print(f"[Tickets] No matching ticket found for message {payload.message_id}")

    async def finalize_ticket(self, guild_id, ticket_id):
        ticket = get_ticket(ticket_id)
        if not ticket:
            print(f"[Tickets] Ticket {ticket_id} not found during finalization")
            return

        print(f"[Tickets] Finalizing ticket {ticket_id}")
        
        ticket["status"] = "APPROVED"
        ticket["approved_members"] = []
        ticket["approval_message_id"] = None

        save_ticket(ticket_id, ticket)

        await update_transcript(
            self.bot,
            ticket_id,
            ticket,
            "🟢 APPROVED"
        )

        # Send DM to ticket creator
        await send_transcript_dm(
            self.bot,
            ticket["created_by"],
            ticket_id,
            ticket,
            "APPROVED"
        )

        guild = self.bot.get_guild(guild_id)
        if guild:
            channel = discord.utils.get(guild.text_channels, name=f"ticket-{ticket_id}")
            if channel:
                await channel.delete(reason="Study group approved")

            # Create role and voice channel
            role = await create_study_role(guild, ticket)
            await assign_role_to_members(guild, role, ticket["members"])
            await create_private_voice_channel(guild, role, ticket)
        
        print(f"[Tickets] Ticket {ticket_id} finalized successfully")


# =================================================
# Role and voice channel creation
# =================================================

async def create_study_role(guild, ticket):
    role_name = f"SG_{ticket['group_name']}"

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

        tid = next_ticket_id()

        ticket = {
            "group_name": self.group_name,
            "level": self.level,
            "member_count": self.member_count,
            "members": self.members,
            "created_by": self.creator.id,
            "status": "OPEN",
            "claimed_by": None,
            "cancelled_by": None,
            "cancelled_at": None,
            "cancellation_reason": None,
            "approval_message_id": None,
            "approved_members": [],
            "transcript_message_id": None,
        }

        ticket["transcript_message_id"] = await post_transcript(
            interaction.client, tid, ticket
        )

        save_ticket(tid, ticket)

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Ticket Created",
                description=f"Ticket **#{tid}** created successfully.",
                color=0x2ECC71
            ),
            view=None
        )


# =================================================
# Select menus (2–5 enforced)
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