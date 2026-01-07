import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import asyncio
import io
import config

from services.database import (
    get_issue_ticket,
    get_all_issue_tickets,
    save_issue_ticket,
    next_issue_ticket_id,
    export_issue_tickets_json,
    get_issue_tickets_by_status,
)

# You'll need to add these to config.py:
# ISSUE_TICKETS_CHANNEL_ID = your_channel_id  # The main channel where threads will be created
# ISSUE_TRANSCRIPTS_CHANNEL_ID = your_channel_id
# MOD_ROLE_ID = your_mod_role_id

# =================================================
# Transcript Helpers
# =================================================

async def post_issue_transcript(bot, ticket_id, ticket):
    """Post initial transcript for issue ticket"""
    channel = bot.get_channel(config.ISSUE_TRANSCRIPTS_CHANNEL_ID)
    if not channel:
        return None

    # Color based on priority
    colors = {
        "Low": 0x95A5A6,      # Gray
        "Medium": 0xF39C12,   # Orange
        "High": 0xE74C3C,     # Red
        "Critical": 0x9B59B6  # Purple
    }

    embed = discord.Embed(
        title=f"🎫 Issue Ticket {ticket_id}",
        color=colors.get(ticket["priority"], 0x95A5A6),
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="Category", value=ticket["category"], inline=True)
    embed.add_field(name="Priority", value=ticket["priority"], inline=True)
    embed.add_field(name="Anonymous", value="Yes" if ticket["anonymous"] else "No", inline=True)
    embed.add_field(name="Reported By", value=f"<@{ticket['created_by']}>", inline=False)
    
    if ticket.get("reported_user"):
        embed.add_field(name="Reported User", value=f"<@{ticket['reported_user']}>", inline=False)
    
    embed.add_field(name="Description", value=ticket["description"][:1024], inline=False)
    embed.add_field(name="Thread", value=f"<#{ticket['thread_id']}>", inline=False)
    embed.add_field(name="Status", value="🟡 OPEN - Awaiting Mod Review", inline=False)

    msg = await channel.send(embed=embed, view=IssueTranscriptView(ticket_id))
    return str(msg.id)


async def update_issue_transcript(bot, ticket_id, ticket, status_text, additional_info=None):
    """Update issue transcript with new status"""
    channel = bot.get_channel(config.ISSUE_TRANSCRIPTS_CHANNEL_ID)
    if not channel:
        return

    try:
        msg = await channel.fetch_message(int(ticket["transcript_message_id"]))
    except (discord.NotFound, ValueError, TypeError):
        return

    embed = msg.embeds[0]
    
    # Update status field
    for i, field in enumerate(embed.fields):
        if field.name == "Status":
            embed.set_field_at(i, name="Status", value=status_text, inline=False)
            break
    
    # Add additional info if provided
    if additional_info:
        embed.add_field(name="Updates", value=additional_info, inline=False)
    
    # Remove buttons if closed
    view = None if ticket["status"] in ["RESOLVED", "CLOSED", "INVALID"] else IssueTranscriptView(ticket_id)
    
    await msg.edit(embed=embed, view=view)


# =================================================
# Create Private Thread
# =================================================

async def create_issue_thread(guild, ticket_id, ticket, mod_role, tickets_channel):
    """Create private thread for issue discussion"""
    
    # Create the private thread
    thread = await tickets_channel.create_thread(
        name=f"🎫 {ticket_id} - {ticket['category']}",
        type=discord.ChannelType.private_thread,
        auto_archive_duration=10080,  # 7 days
        reason=f"Issue ticket {ticket_id} created"
    )

    # Add moderators (they can see all private threads in the channel)
    # Add creator if not anonymous
    if not ticket["anonymous"]:
        creator = guild.get_member(ticket["created_by"])
        if creator:
            try:
                await thread.add_user(creator)
            except discord.HTTPException:
                pass

    # Get all members with mod role and add them
    for member in guild.members:
        if mod_role in member.roles:
            try:
                await thread.add_user(member)
            except discord.HTTPException:
                continue

    # Send initial message in thread
    embed = discord.Embed(
        title=f"Issue Ticket {ticket_id}",
        description=ticket["description"],
        color=0xE74C3C,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(name="Category", value=ticket["category"], inline=True)
    embed.add_field(name="Priority", value=ticket["priority"], inline=True)
    
    if ticket.get("reported_user"):
        embed.add_field(name="Reported User", value=f"<@{ticket['reported_user']}>", inline=False)
    
    if not ticket["anonymous"]:
        embed.add_field(name="Reported By", value=f"<@{ticket['created_by']}>", inline=False)
    else:
        embed.add_field(name="Reported By", value="*Anonymous*", inline=False)
    
    embed.set_footer(text="Mods: Use the buttons below to manage this ticket")
    
    await thread.send(
        content=f"{mod_role.mention} - New issue ticket requires attention!",
        embed=embed,
        view=IssueThreadActionsView(ticket_id)
    )
    
    return thread


# =================================================
# Issue Creation Modal
# =================================================

class IssueTicketModal(discord.ui.Modal, title="Report an Issue"):
    description = discord.ui.TextInput(
        label="Describe the Issue",
        style=discord.TextStyle.paragraph,
        placeholder="Provide detailed information about the issue...",
        required=True,
        max_length=1000
    )

    def __init__(self, category, priority, anonymous, reported_user=None):
        super().__init__()
        self.category = category
        self.priority = priority
        self.anonymous = anonymous
        self.reported_user = reported_user

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        ticket_id = next_issue_ticket_id()
        
        ticket = {
            "category": self.category,
            "priority": self.priority,
            "description": self.description.value,
            "created_by": interaction.user.id,
            "anonymous": self.anonymous,
            "reported_user": self.reported_user,
            "status": "OPEN",
            "claimed_by": None,
            "escalated": False,
            "escalated_by": None,
            "resolution": None,
            "created_at": datetime.utcnow().isoformat(),
            "thread_id": None,
            "transcript_message_id": None,
        }

        # Get the tickets channel
        tickets_channel = interaction.guild.get_channel(config.ISSUE_TICKETS_CHANNEL_ID)
        if not tickets_channel:
            await interaction.followup.send("❌ Issue tickets channel not found.", ephemeral=True)
            return

        # Create private thread
        mod_role = interaction.guild.get_role(config.MOD_ROLE_ID)
        thread = await create_issue_thread(
            interaction.guild, ticket_id, ticket, mod_role, tickets_channel
        )

        ticket["thread_id"] = thread.id

        # Post transcript
        ticket["transcript_message_id"] = await post_issue_transcript(
            interaction.client, ticket_id, ticket
        )

        # Store ticket in database
        save_issue_ticket(ticket_id, ticket)

        await interaction.followup.send(
            f"✅ Issue ticket **{ticket_id}** created successfully.\n"
            f"{'Your identity is hidden from the thread.' if self.anonymous else f'Thread created: {thread.mention}'}\n\n"
            f"Moderators have been notified and will review your ticket soon.",
            ephemeral=True
        )

        print(f"[IssueTickets] Created {ticket_id} by user {interaction.user.id} - Thread: {thread.id}")


# =================================================
# Issue Creation Form View
# =================================================

class IssueTicketFormView(discord.ui.View):
    def __init__(self, creator):
        super().__init__(timeout=300)
        self.creator = creator
        self.category = None
        self.priority = "Medium"
        self.anonymous = False
        self.reported_user = None

        self.embed = discord.Embed(
            title="Report an Issue",
            description="Please select the options below before submitting.",
            color=0xE74C3C
        )
        self.update_embed()

        self.add_item(CategorySelect())
        self.add_item(PrioritySelect())
        self.add_item(ReportedUserSelect())

    def update_embed(self):
        self.embed.clear_fields()
        self.embed.add_field(name="Category", value=self.category or "—", inline=True)
        self.embed.add_field(name="Priority", value=self.priority, inline=True)
        self.embed.add_field(name="Anonymous", value="Yes" if self.anonymous else "No", inline=True)
        self.embed.add_field(
            name="Reported User",
            value=f"<@{self.reported_user}>" if self.reported_user else "None (General Issue)",
            inline=False
        )

    @discord.ui.button(label="🕵️ Make Anonymous", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_anonymous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.anonymous = not self.anonymous
        button.label = "🕵️ Anonymous: ON" if self.anonymous else "🕵️ Make Anonymous"
        button.style = discord.ButtonStyle.success if self.anonymous else discord.ButtonStyle.secondary
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label="Submit Issue", style=discord.ButtonStyle.danger, row=4)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.category:
            await interaction.response.send_message("❌ Please select a category.", ephemeral=True)
            return

        await interaction.response.send_modal(
            IssueTicketModal(
                self.category,
                self.priority,
                self.anonymous,
                self.reported_user
            )
        )


class CategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select Issue Category",
            options=[
                discord.SelectOption(label="🚫 Harassment/Bullying", value="Harassment", emoji="🚫"),
                discord.SelectOption(label="💬 Toxic Behavior", value="Toxic Behavior", emoji="💬"),
                discord.SelectOption(label="🔞 Inappropriate Content", value="Inappropriate Content", emoji="🔞"),
                discord.SelectOption(label="🤖 Spam/Bot Activity", value="Spam", emoji="🤖"),
                discord.SelectOption(label="⚠️ Rule Violation", value="Rule Violation", emoji="⚠️"),
                discord.SelectOption(label="💡 Suggestion/Feedback", value="Suggestion", emoji="💡"),
                discord.SelectOption(label="❓ Other", value="Other", emoji="❓"),
            ]
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.category = self.values[0]
        self.view.update_embed()
        await interaction.response.edit_message(embed=self.view.embed, view=self.view)


class PrioritySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select Priority (Default: Medium)",
            options=[
                discord.SelectOption(label="Low Priority", value="Low", emoji="🟢"),
                discord.SelectOption(label="Medium Priority", value="Medium", emoji="🟡", default=True),
                discord.SelectOption(label="High Priority", value="High", emoji="🟠"),
                discord.SelectOption(label="Critical", value="Critical", emoji="🔴"),
            ]
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.priority = self.values[0]
        self.view.update_embed()
        await interaction.response.edit_message(embed=self.view.embed, view=self.view)


class ReportedUserSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Select user to report (optional)", min_values=0, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.reported_user = self.values[0].id if self.values else None
        self.view.update_embed()
        await interaction.response.edit_message(embed=self.view.embed, view=self.view)


# =================================================
# Thread Action Buttons (For Mods)
# =================================================

class IssueThreadActionsView(discord.ui.View):
    def __init__(self, ticket_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.primary, emoji="✋", custom_id="issue_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is mod
        mod_role = interaction.guild.get_role(config.MOD_ROLE_ID)
        if mod_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
            return

        ticket = get_issue_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("⚠️ Ticket not found.", ephemeral=True)
            return

        if ticket["claimed_by"]:
            await interaction.response.send_message(
                f"⚠️ This ticket is already claimed by <@{ticket['claimed_by']}>.",
                ephemeral=True
            )
            return

        ticket["claimed_by"] = interaction.user.id
        ticket["status"] = "IN_PROGRESS"

        save_issue_ticket(self.ticket_id, ticket)

        await update_issue_transcript(
            interaction.client,
            self.ticket_id,
            ticket,
            f"🔵 IN PROGRESS - Claimed by <@{interaction.user.id}>"
        )

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} has claimed this ticket and is now handling it.",
            allowed_mentions=discord.AllowedMentions.none()
        )

    @discord.ui.button(label="Escalate to Admin", style=discord.ButtonStyle.danger, emoji="⬆️", custom_id="issue_escalate")
    async def escalate(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions
        mod_role = interaction.guild.get_role(config.MOD_ROLE_ID)
        admin_role = interaction.guild.get_role(config.ADMIN_ROLE_ID)
        
        if mod_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
            return

        ticket = get_issue_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("⚠️ Ticket not found.", ephemeral=True)
            return

        if ticket["escalated"]:
            await interaction.response.send_message("⚠️ This ticket is already escalated.", ephemeral=True)
            return

        ticket["escalated"] = True
        ticket["escalated_by"] = interaction.user.id
        ticket["status"] = "ESCALATED"

        save_issue_ticket(self.ticket_id, ticket)

        # Add all admins to the thread
        thread = interaction.channel
        if isinstance(thread, discord.Thread):
            for member in interaction.guild.members:
                if admin_role in member.roles:
                    try:
                        await thread.add_user(member)
                    except discord.HTTPException:
                        continue

        await update_issue_transcript(
            interaction.client,
            self.ticket_id,
            ticket,
            f"🔴 ESCALATED - Escalated by <@{interaction.user.id}>"
        )

        await interaction.response.send_message(
            f"⬆️ {admin_role.mention} This ticket has been escalated and requires admin attention.\n"
            f"Escalated by: {interaction.user.mention}",
            allowed_mentions=discord.AllowedMentions(roles=True)
        )

    @discord.ui.button(label="Resolve Ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="issue_resolve")
    async def resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions
        mod_role = interaction.guild.get_role(config.MOD_ROLE_ID)
        if mod_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Moderators/Admins only.", ephemeral=True)
            return

        ticket = get_issue_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("⚠️ Ticket not found.", ephemeral=True)
            return

        await interaction.response.send_modal(
            ResolveTicketModal(self.ticket_id, interaction.client)
        )

    @discord.ui.button(label="Mark as Invalid", style=discord.ButtonStyle.secondary, emoji="❌", custom_id="issue_invalid")
    async def mark_invalid(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions
        mod_role = interaction.guild.get_role(config.MOD_ROLE_ID)
        if mod_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Moderators/Admins only.", ephemeral=True)
            return

        ticket = get_issue_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("⚠️ Ticket not found.", ephemeral=True)
            return

        await interaction.response.send_modal(
            InvalidTicketModal(self.ticket_id, interaction.client)
        )


# =================================================
# Resolution Modals
# =================================================

class ResolveTicketModal(discord.ui.Modal, title="Resolve Issue Ticket"):
    resolution = discord.ui.TextInput(
        label="Resolution Summary",
        style=discord.TextStyle.paragraph,
        placeholder="Describe how this issue was resolved...",
        required=True,
        max_length=500
    )

    def __init__(self, ticket_id, bot):
        super().__init__()
        self.ticket_id = ticket_id
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        ticket = get_issue_ticket(self.ticket_id)
        if not ticket:
            await interaction.followup.send("⚠️ Ticket not found.", ephemeral=True)
            return

        ticket["status"] = "RESOLVED"
        ticket["resolution"] = self.resolution.value
        ticket["resolved_by"] = interaction.user.id
        ticket["resolved_at"] = datetime.utcnow().isoformat()

        save_issue_ticket(self.ticket_id, ticket)

        await update_issue_transcript(
            self.bot,
            self.ticket_id,
            ticket,
            f"🟢 RESOLVED by <@{interaction.user.id}>",
            f"**Resolution:** {self.resolution.value}"
        )

        # Notify ticket creator via DM
        try:
            creator = await self.bot.fetch_user(ticket["created_by"])
            embed = discord.Embed(
                title=f"✅ Your Issue Ticket {self.ticket_id} Has Been Resolved",
                description=self.resolution.value,
                color=0x2ECC71,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="CA Study Space • Issue Resolution")
            await creator.send(embed=embed)
        except:
            pass

        await interaction.followup.send(
            f"✅ Ticket {self.ticket_id} marked as resolved.\n"
            f"**Resolution:** {self.resolution.value}\n\n"
            f"The thread will be archived and locked in 30 seconds."
        )

        # Archive and lock thread after 30 seconds
        await asyncio.sleep(30)
        thread = interaction.channel
        if isinstance(thread, discord.Thread):
            try:
                await thread.edit(archived=True, locked=True)
            except:
                pass


class InvalidTicketModal(discord.ui.Modal, title="Mark as Invalid"):
    reason = discord.ui.TextInput(
        label="Reason for Invalidity",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this ticket invalid? (spam, false report, etc.)",
        required=True,
        max_length=300
    )

    def __init__(self, ticket_id, bot):
        super().__init__()
        self.ticket_id = ticket_id
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        ticket = get_issue_ticket(self.ticket_id)
        if not ticket:
            await interaction.followup.send("⚠️ Ticket not found.", ephemeral=True)
            return

        ticket["status"] = "INVALID"
        ticket["resolution"] = f"Marked as invalid: {self.reason.value}"
        ticket["resolved_by"] = interaction.user.id

        save_issue_ticket(self.ticket_id, ticket)

        await update_issue_transcript(
            self.bot,
            self.ticket_id,
            ticket,
            f"⚫ INVALID - Marked by <@{interaction.user.id}>",
            f"**Reason:** {self.reason.value}"
        )

        await interaction.followup.send(
            f"⚫ Ticket {self.ticket_id} marked as invalid.\n"
            f"**Reason:** {self.reason.value}\n\n"
            f"Thread will be archived in 10 seconds."
        )

        await asyncio.sleep(10)
        thread = interaction.channel
        if isinstance(thread, discord.Thread):
            try:
                await thread.edit(archived=True, locked=True)
            except:
                pass


# =================================================
# Transcript View (Admin Actions)
# =================================================

class IssueTranscriptView(discord.ui.View):
    def __init__(self, ticket_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id

    @discord.ui.button(label="Jump to Thread", style=discord.ButtonStyle.primary, custom_id="issue_jump_thread")
    async def jump_thread(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = get_issue_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("⚠️ Ticket not found.", ephemeral=True)
            return

        thread = interaction.guild.get_thread(int(ticket["thread_id"]))
        if not thread:
            await interaction.response.send_message("⚠️ Thread not found or archived.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Thread: {thread.mention}",
            ephemeral=True
        )

    @discord.ui.button(label="View Details", style=discord.ButtonStyle.secondary, custom_id="issue_view_details")
    async def view_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = get_issue_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("⚠️ Ticket not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Issue Ticket {self.ticket_id} - Full Details",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="Status", value=ticket["status"], inline=True)
        embed.add_field(name="Category", value=ticket["category"], inline=True)
        embed.add_field(name="Priority", value=ticket["priority"], inline=True)
        embed.add_field(name="Created By", value=f"<@{ticket['created_by']}>", inline=True)
        
        if ticket["claimed_by"]:
            embed.add_field(name="Claimed By", value=f"<@{ticket['claimed_by']}>", inline=True)
        
        if ticket["escalated"]:
            embed.add_field(name="Escalated By", value=f"<@{ticket['escalated_by']}>", inline=True)
        
        embed.add_field(name="Description", value=ticket["description"], inline=False)
        
        if ticket.get("resolution"):
            embed.add_field(name="Resolution", value=ticket["resolution"], inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


# =================================================
# Entry Button for Users
# =================================================

class IssueTicketEntryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Report an Issue",
        emoji="🚨",
        style=discord.ButtonStyle.danger,
        custom_id="cssbot_report_issue"
    )
    async def report_issue(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = IssueTicketFormView(interaction.user)
        await interaction.response.send_message(
            embed=view.embed,
            view=view,
            ephemeral=True
        )


# =================================================
# Cog
# =================================================

class IssueTickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup_issue_reporter",
        description="Setup the issue reporting system in this channel"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_reporter(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🚨 Report an Issue",
            description=(
                "If you're experiencing harassment, toxicity, or have any concerns, "
                "please report them here.\n\n"
                "**Your report will be:**\n"
                "✅ Reviewed by moderators privately in a thread\n"
                "✅ Handled confidentially\n"
                "✅ Escalated to admins if needed\n\n"
                "You can choose to report anonymously."
            ),
            color=0xE74C3C
        )
        embed.set_footer(text="We take all reports seriously • CA Study Space")

        await interaction.response.send_message(
            embed=embed,
            view=IssueTicketEntryView()
        )

        # Register persistent view
        self.bot.add_view(IssueTicketEntryView())

    @app_commands.command(
        name="export_issue_tickets",
        description="Export all issue tickets as JSON for audit"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def export_issue_tickets(self, interaction: discord.Interaction):
        json_data = export_issue_tickets_json()

        fp = io.StringIO(json_data)
        file = discord.File(fp, filename=f"issue_tickets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")

        await interaction.response.send_message(
            content="📊 Issue ticket data export:",
            file=file,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(IssueTickets(bot))