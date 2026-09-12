import os
import io
import sys
import sqlite3
import datetime
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageOps
import aiohttp

# Load environment variables
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
COLOR_HEX = os.getenv("EMBED_COLOR", "00A2FF").replace("#", "")
EMBED_COLOR = int(COLOR_HEX, 16)

# Database Setup
DB_PATH = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
        (guild_id, user_id, moderator_id, reason, now)
    )
    conn.commit()
    conn.close()

def get_warnings(guild_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, moderator_id, reason, timestamp FROM warnings WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

# Helper for Ordinals (1st, 2nd, 3rd, 54th)
def ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

# Setup Bot
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== WELCOME CARD GENERATOR ====================

async def create_welcome_card(member: discord.Member) -> io.BytesIO:
    width, height = 800, 260
    card = Image.new("RGBA", (width, height), (15, 17, 23, 255))
    draw = ImageDraw.Draw(card)

    # Outer white border (matching screenshot design)
    draw.rectangle([5, 5, width - 6, height - 6], outline=(255, 255, 255, 255), width=5)

    # Inner gradient / background accents
    for i in range(12, height - 12):
        alpha = int(255 * (1 - (i / height) * 0.4))
        draw.line([(12, i), (width - 13, i)], fill=(20, 28, 42, alpha))

    # Fetch avatar
    avatar_url = member.display_avatar.with_format("png").url
    async with aiohttp.ClientSession() as session:
        async with session.get(avatar_url) as resp:
            if resp.status == 200:
                avatar_bytes = await resp.read()
                avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            else:
                avatar_img = Image.new("RGBA", (150, 150), (100, 100, 100, 255))

    avatar_size = 160
    avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

    # Create circular mask for avatar
    mask = Image.new("L", (avatar_size, avatar_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)

    # Draw circle ring for avatar on card
    avatar_x, avatar_y = 50, 50
    draw.ellipse(
        [avatar_x - 6, avatar_y - 6, avatar_x + avatar_size + 6, avatar_y + avatar_size + 6],
        fill=(255, 255, 255, 255)
    )

    card.paste(avatar_img, (avatar_x, avatar_y), mask)

    # Fonts loading with fallbacks
    try:
        font_large = ImageFont.truetype("arial.ttf", 28)
        font_small = ImageFont.truetype("arial.ttf", 22)
    except IOError:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Text rendering
    text_x = 240
    user_name = member.display_name
    guild_name = member.guild.name
    count_str = ordinal(member.guild.member_count)

    line1 = f"Welcome {user_name}"
    line2 = f"to {guild_name} you are the {count_str} member!"

    draw.text((text_x, 90), line1, fill=(255, 255, 255, 255), font=font_large)
    draw.text((text_x, 130), line2, fill=(240, 240, 240, 255), font=font_small)

    buffer = io.BytesIO()
    card.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# ==================== TICKET SYSTEM VIEWS ====================

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ebl_ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Closing ticket and generating transcript...", ephemeral=True)

        channel = interaction.channel
        guild = interaction.guild

        # Generate Transcript Text
        messages = []
        async for msg in channel.history(limit=500, oldest_first=True):
            time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = msg.content if msg.content else "[No Text Content]"
            if msg.attachments:
                att_urls = " ".join([a.url for a in msg.attachments])
                content += f" (Attachments: {att_urls})"
            messages.append(f"[{time_str}] {msg.author} ({msg.author.id}): {content}")

        transcript_text = f"=== TICKET TRANSCRIPT FOR {channel.name.upper()} ===\n"
        transcript_text += f"Closed By: {interaction.user} ({interaction.user.id})\n"
        transcript_text += f"Date: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        transcript_text += f"Total Messages: {len(messages)}\n"
        transcript_text += "=" * 50 + "\n\n"
        transcript_text += "\n".join(messages)

        transcript_file = discord.File(
            io.BytesIO(transcript_text.encode("utf-8")),
            filename=f"transcript-{channel.name}.txt"
        )

        # Send transcript to log channel if set
        if LOG_CHANNEL_ID != 0:
            log_chan = guild.get_channel(LOG_CHANNEL_ID)
            if log_chan:
                log_embed = discord.Embed(
                    title="📄 Ticket Transcript Generated",
                    description=f"**Ticket:** {channel.name}\n**Closed by:** {interaction.user.mention}",
                    color=EMBED_COLOR,
                    timestamp=datetime.datetime.utcnow()
                )
                await log_chan.send(embed=log_embed, file=transcript_file)

        await asyncio.sleep(3)
        await channel.delete(reason="Ticket Closed")

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.success, emoji="✋", custom_id="ebl_ticket_claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="✋ Ticket Claimed",
            description=f"This ticket has been claimed by {interaction.user.mention}. They will assist you shortly!",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed)


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Apply for Member",
                value="apply_member",
                description="Apply for Fortnite Esports Roster",
                emoji="⚔️"
            ),
            discord.SelectOption(
                label="Apply for Staff",
                value="apply_staff",
                description="Apply for Management or Moderation Team",
                emoji="🛡️"
            ),
            discord.SelectOption(
                label="General Questions & Support",
                value="general_support",
                description="Get help or ask any questions",
                emoji="❓"
            )
        ]
        super().__init__(
            placeholder="Select a category to open a ticket...",
            min_values=1,
            max_values=1,
            custom_id="ebl_ticket_select"
        )
        self.options = options

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        category_type = self.values[0]

        type_names = {
            "apply_member": "member-apply",
            "apply_staff": "staff-apply",
            "general_support": "support"
        }

        channel_name = f"{type_names.get(category_type, 'ticket')}-{user.name.lower()}"

        # Check existing channel
        existing = discord.utils.get(guild.channels, name=channel_name)
        if existing:
            await interaction.response.send_message(f"❌ You already have an open ticket: {existing.mention}", ephemeral=True)
            return

        category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID != 0 else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
        }

        if STAFF_ROLE_ID != 0:
            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket opened by {user}"
        )

        title_map = {
            "apply_member": "⚔️ Member Application Ticket",
            "apply_staff": "🛡️ Staff Application Ticket",
            "general_support": "❓ Support & General Inquiries"
        }

        desc_map = {
            "apply_member": f"Welcome {user.mention}!\nPlease state your Fortnite IGN, age, region, and links to your tracker/highlights.",
            "apply_staff": f"Welcome {user.mention}!\nPlease state your age, prior staff experience, timezone, and why you want to join our staff team.",
            "general_support": f"Welcome {user.mention}!\nPlease describe your issue or question in detail and staff will assist you shortly."
        }

        embed = discord.Embed(
            title=title_map.get(category_type, "Ticket Support"),
            description=desc_map.get(category_type, f"Welcome {user.mention}! Staff will assist you shortly."),
            color=EMBED_COLOR
        )
        embed.set_footer(text="Expand By Legacy™ • Esports Ticket System")

        await ticket_channel.send(content=f"{user.mention} Welcome!", embed=embed, view=TicketControlView())
        await interaction.response.send_message(f"✅ Ticket created! Head over to {ticket_channel.mention}", ephemeral=True)


class TicketLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# ==================== BOT EVENTS ====================

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")
    bot.add_view(TicketLaunchView())
    bot.add_view(TicketControlView())
    try:
        synced = await bot.tree.sync()
        print(f"[SLASH] Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"[SLASH ERROR] Failed to sync commands: {e}")

@bot.event
async def on_member_join(member: discord.Member):
    count_str = ordinal(member.guild.member_count)
    
    # 1. Channel Welcome
    if WELCOME_CHANNEL_ID != 0:
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            welcome_text = f"Welcome {member.mention} to **{member.guild.name}**! You are the {count_str} member!"
            try:
                card_buffer = await create_welcome_card(member)
                file = discord.File(card_buffer, filename="welcome.png")
                await channel.send(content=welcome_text, file=file)
            except Exception as e:
                print(f"[WELCOME CARD ERROR] {e}")
                await channel.send(content=welcome_text)

    # 2. DM Welcome
    try:
        dm_embed = discord.Embed(
            title=f"Welcome to {member.guild.name}! 🏆",
            description=(
                f"Hey {member.name}, welcome to the official **{member.guild.name}** Discord server!\n\n"
                f"• Check out our guidelines and rules.\n"
                f"• Want to join our Fortnite team? Open a ticket in the server!\n"
                f"• Enjoy your stay and grind to the top! 🚀"
            ),
            color=EMBED_COLOR
        )
        dm_embed.set_footer(text=f"Expand By Legacy™ • Member #{member.guild.member_count}")
        await member.send(embed=dm_embed)
    except Exception as e:
        print(f"[DM WELCOME FAILED] Could not send DM to {member}: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # Echo feature: Message starting with '*'
    if message.content.startswith("*") and len(message.content) > 1:
        content_to_send = message.content[1:].strip()
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        await message.channel.send(content_to_send)
        return

    await bot.process_commands(message)

# ==================== SLASH COMMANDS ====================

@bot.tree.command(name="setup-tickets", description="Deploy the interactive ticket creation embed")
@app_commands.checks.has_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🏆 Expand By Legacy™ • Support & Applications",
        description=(
            "Need help or want to join our esports roster?\n"
            "Select an option from the menu below to open a private ticket channel.\n\n"
            "⚔️ **Apply for Member** - Join our Fortnite roster\n"
            "🛡️ **Apply for Staff** - Join team management\n"
            "❓ **General Questions & Support** - Get assistance"
        ),
        color=EMBED_COLOR
    )
    embed.set_footer(text="Expand By Legacy™ • Official Esports Bot")
    await interaction.channel.send(embed=embed, view=TicketLaunchView())
    await interaction.response.send_message("✅ Ticket panel created successfully!", ephemeral=True)

@bot.tree.command(name="rules", description="Display server guidelines and rules")
async def rules_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Server Guidelines & Rules • Expand By Legacy™",
        description=(
            "Welcome to **Expand By Legacy™**! Please follow these guidelines to ensure a competitive and safe environment:\n\n"
            "**1. Respect Everyone**\nNo toxicity, hate speech, racism, or unnecessary harassment.\n\n"
            "**2. Competitive Integrity**\nNo cheating, exploiting, or teaming in scrims/tournaments.\n\n"
            "**3. No Self-Promotion**\nDo not post stream/social links outside of designated promo channels.\n\n"
            "**4. Ticket Etiquette**\nOnly open tickets when necessary. Do not spam staff members.\n\n"
            "**5. Follow Discord TOS**\nAdhere strictly to Discord Terms of Service and Community Guidelines."
        ),
        color=EMBED_COLOR
    )
    embed.set_footer(text="Expand By Legacy™ • Play Fair & Grind Hard")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.checks.has_permissions(kick_members=True)
async def kick_user(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="👢 Member Kicked",
            description=f"**User:** {member.mention} ({member.id})\n**Reason:** {reason}\n**Moderator:** {interaction.user.mention}",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to kick user: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.checks.has_permissions(ban_members=True)
async def ban_user(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="🔨 Member Banned",
            description=f"**User:** {member.mention} ({member.id})\n**Reason:** {reason}\n**Moderator:** {interaction.user.mention}",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to ban user: {e}", ephemeral=True)

@bot.tree.command(name="unban", description="Unban a user by ID")
@app_commands.checks.has_permissions(ban_members=True)
async def unban_user(interaction: discord.Interaction, user_id: str):
    try:
        uid = int(user_id)
        user = await bot.fetch_user(uid)
        await interaction.guild.unban(user)
        embed = discord.Embed(
            title="🔓 User Unbanned",
            description=f"**User:** {user.name} ({user.id})\n**Moderator:** {interaction.user.mention}",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to unban user: {e}", ephemeral=True)

@bot.tree.command(name="timeout", description="Mute / Timeout a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout_user(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    try:
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        embed = discord.Embed(
            title="⏳ Member Timed Out",
            description=f"**User:** {member.mention}\n**Duration:** {minutes} minutes\n**Reason:** {reason}\n**Moderator:** {interaction.user.mention}",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to timeout member: {e}", ephemeral=True)

@bot.tree.command(name="untimeout", description="Remove timeout from a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout_user(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None)
        embed = discord.Embed(
            title="🔊 Timeout Removed",
            description=f"**User:** {member.mention}\n**Moderator:** {interaction.user.mention}",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to remove timeout: {e}", ephemeral=True)

@bot.tree.command(name="clear", description="Purge messages in bulk")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear_messages(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Please specify an amount between 1 and 100.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Cleared {len(deleted)} message(s).", ephemeral=True)

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn_user(interaction: discord.Interaction, member: discord.Member, reason: str):
    add_warning(interaction.guild.id, member.id, interaction.user.id, reason)
    embed = discord.Embed(
        title="⚠️ Member Warned",
        description=f"**User:** {member.mention}\n**Reason:** {reason}\n**Moderator:** {interaction.user.mention}",
        color=EMBED_COLOR
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warnings", description="View warnings for a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def view_warnings(interaction: discord.Interaction, member: discord.Member):
    warns = get_warnings(interaction.guild.id, member.id)
    if not warns:
        await interaction.response.send_message(f"ℹ️ {member.mention} has no warnings.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"⚠️ Warnings for {member.display_name} ({len(warns)})",
        color=EMBED_COLOR
    )
    for wid, mod_id, reason, ts in warns:
        mod = interaction.guild.get_member(mod_id)
        mod_name = mod.mention if mod else f"ID: {mod_id}"
        embed.add_field(name=f"Warn #{wid}", value=f"**Reason:** {reason}\n**By:** {mod_name}\n**Date:** {ts[:10]}", inline=False)

    await interaction.response.send_message(embed=embed)

# Main Entry Point
if __name__ == "__main__":
    if not TOKEN:
        print("[ERROR] DISCORD_TOKEN missing in environment variables!")
        sys.exit(1)
    bot.run(TOKEN)
