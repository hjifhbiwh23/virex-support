import discord
from discord.ext import commands
import asyncio

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PREFIX = "$"
SILENT_PREFIX = "*"          # Messages starting with * are deleted and re-sent by the bot
BAN_REQUEST_CHANNEL_ID = 1504101352475725945   # ← Replace with your channel ID (int)
STAFF_ROLE_NAME = "T Staff"  # ← Minimum role for all commands (case-insensitive)

# ─── BOT SETUP ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def has_staff_role(member: discord.Member) -> bool:
    """Returns True if the member has at least the Staff role."""
    role_names = [r.name.lower() for r in member.roles]
    return STAFF_ROLE_NAME.lower() in role_names

async def staff_check(ctx) -> bool:
    """Sends an error message and returns False if the user is not Staff."""
    if not has_staff_role(ctx.author):
        embed = discord.Embed(
            title="❌ No Permission",
            description="You need at least the **t staff** role to use this command.",
            color=0xFF4444
        )
        await ctx.send(embed=embed, delete_after=5)
        await ctx.message.delete()
        return False
    return True

# ─── GHOST SPEAK (*) ─────────────────────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Staff messages starting with * are deleted and re-sent by the bot
    if message.content.startswith(SILENT_PREFIX):
        if not has_staff_role(message.author):
            return  # Ignore non-staff silently

        content = message.content[len(SILENT_PREFIX):].strip()

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        if content:
            await message.channel.send(content)
        return  # Do not process commands

    await bot.process_commands(message)

# ─── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="virex.gg | $manual"))

# ─── COMMANDS ─────────────────────────────────────────────────────────────────

# $manual
@bot.command(name="manual")
async def manual(ctx):
    if not await staff_check(ctx): return
    await ctx.message.delete()

    embed = discord.Embed(
        title="📖 AnyDesk Manual — Virex",
        color=0x5865F2
    )
    embed.add_field(
        name="💰 Perm Guide Assistance",
        value=(
            "For **€20** you can hire a Staff member *(NOT Trial Staff)* to perform "
            "the Perm Guide for you via **AnyDesk**.\n\n"
            "Ideal for those who don't feel confident enough to run the guide themselves. "
            "However, the guide is simple enough for most people."
        ),
        inline=False
    )
    embed.add_field(
        name="⚠️ Note",
        value=(
            "This is **different** from the ASUS Manual. "
            "If you don't have an ASUS, ignore this point."
        ),
        inline=False
    )
    embed.set_footer(text="Virex Team")
    await ctx.send(embed=embed)


# $activate
@bot.command(name="activate")
async def activate(ctx):
    if not await staff_check(ctx): return
    await ctx.message.delete()

    embed = discord.Embed(
        title="🪟 Windows Activation Guide",
        description="Follow the steps below to activate Windows.",
        color=0x00B4D8
    )
    embed.add_field(
        name="1️⃣ Open PowerShell as Administrator",
        value="Press **Windows**, type `PowerShell`, right-click → **Run as Administrator**",
        inline=False
    )
    embed.add_field(
        name="2️⃣ Run the command",
        value="```irm https://get.activated.win/ | iex```",
        inline=False
    )
    embed.add_field(name="3️⃣ Press `4`", value="​", inline=True)
    embed.add_field(name="4️⃣ Activate Windows → `1`", value="​", inline=True)
    embed.add_field(name="5️⃣ Set up Auto-Renewal → `5`", value="​", inline=True)
    embed.set_footer(text="Virex Team")
    await ctx.send(embed=embed)


# $tempvsperm
@bot.command(name="tempvsperm")
async def tempvsperm(ctx):
    if not await staff_check(ctx): return
    await ctx.message.delete()

    embed = discord.Embed(
        title="🐾 Temp vs. Perm Woofer — What's the Difference?",
        color=0xF4A261
    )
    embed.add_field(
        name="🔒 Permanent Woofer (Perm)",
        value=(
            "- Changes your serials **permanently**\n"
            "- Serials remain unless you receive a **ban** (e.g. for cheating)\n"
            "- Requires a **full Windows reinstall**\n"
            "- Ideal for cheaters who want to go clean or need **long-term security**"
        ),
        inline=False
    )
    embed.add_field(
        name="⏳ Temporary Woofer (Temp)",
        value=(
            "- Only lasts for **one session** (resets after restart)\n"
            "- Must be run again after every reboot\n"
            "- **No** Windows reinstall required\n"
            "- Ideal for DTC games or for **testing**"
        ),
        inline=False
    )
    embed.add_field(
        name="❓ Still unsure?",
        value="Open a ticket in <#1502194775695167500> for personal advice.",
        inline=False
    )
    embed.set_footer(text="Virex Team")
    await ctx.send(embed=embed)


# $proof
@bot.command(name="proof")
async def proof(ctx):
    if not await staff_check(ctx): return
    await ctx.message.delete()

    embed = discord.Embed(
        title="📸 Submit Purchase Proof — How It Works",
        description=(
            "To verify your purchase, you need to submit **proof**. "
            "Follow the instructions below carefully."
        ),
        color=0x2ECC71
    )
    embed.add_field(
        name="📧 1. Email Confirmation",
        value=(
            "- Open your **email** (Gmail, Outlook, etc.)\n"
            "- Search for the **purchase confirmation email** from Virex/the shop\n"
            "- Take a **screenshot** of the full email *(subject, amount & date must be visible)*"
        ),
        inline=False
    )
    embed.add_field(
        name="💳 2. Payment Proof",
        value=(
            "- Screenshot of your **PayPal / Crypto / etc. transaction history**\n"
            "- Amount, date and recipient must be **clearly visible**\n"
            "- You may **redact** personal data (except amount & date)"
        ),
        inline=False
    )
    embed.add_field(
        name="📤 3. Submit Screenshots",
        value=(
            "- Upload **both screenshots** directly into this channel\n"
            "- Add: `$proof` + your **Order ID** (if available)\n"
            "- A Staff member will review your proof"
        ),
        inline=False
    )
    embed.add_field(
        name="⚠️ Important",
        value=(
            "Fake or manipulated screenshots will result in a **permanent ban**.\n"
            "Screenshots must be **unedited** (except redacted personal data)."
        ),
        inline=False
    )
    embed.set_image(url="attachment://proof_guide.png")
    embed.set_footer(text="Virex Team • No Proof = No Activation")

    try:
        file = discord.File("proof_guide.png", filename="proof_guide.png")
        await ctx.send(file=file, embed=embed)
    except FileNotFoundError:
        await ctx.send(embed=embed)


# $ban <user_id> <reason>
@bot.command(name="ban")
async def ban_request(ctx, user_id: str = None, *, reason: str = None):
    if not await staff_check(ctx): return
    await ctx.message.delete()

    if not user_id or not reason:
        embed = discord.Embed(
            title="❌ Incorrect Usage",
            description="Usage: `$ban <user_id> <reason>`\nExample: `$ban 123456789 Cheating on server`",
            color=0xFF4444
        )
        await ctx.send(embed=embed, delete_after=8)
        return

    # Try to resolve the user
    try:
        target_user = await bot.fetch_user(int(user_id))
        user_display = f"{target_user} (`{user_id}`)"
        user_avatar = target_user.display_avatar.url
    except Exception:
        user_display = f"Unknown User (`{user_id}`)"
        user_avatar = None

    ban_embed = discord.Embed(
        title="🔨 Ban Request",
        color=0xFF0000
    )
    ban_embed.add_field(name="👤 User", value=user_display, inline=True)
    ban_embed.add_field(name="🛡️ Requested by", value=f"{ctx.author} (`{ctx.author.id}`)", inline=True)
    ban_embed.add_field(name="📝 Reason", value=reason, inline=False)
    ban_embed.add_field(name="📍 Channel", value=ctx.channel.mention, inline=True)
    ban_embed.set_footer(text=f"User ID: {user_id}")
    ban_embed.timestamp = ctx.message.created_at
    if user_avatar:
        ban_embed.set_thumbnail(url=user_avatar)

    ban_channel = bot.get_channel(BAN_REQUEST_CHANNEL_ID)
    if ban_channel:
        await ban_channel.send(embed=ban_embed)
        confirm = discord.Embed(
            title="✅ Ban Request Sent",
            description=f"Ban request for **{user_display}** has been sent to {ban_channel.mention}.",
            color=0x00FF00
        )
        await ctx.send(embed=confirm, delete_after=5)
    else:
        error = discord.Embed(
            title="⚠️ Channel Not Found",
            description="Ban request channel not configured. Please set `BAN_REQUEST_CHANNEL_ID` in bot.py.",
            color=0xFF8800
        )
        await ctx.send(embed=error, delete_after=8)


# ─── ERROR HANDLING ───────────────────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing arguments. Use `$help` for help.", delete_after=5)
    else:
        print(f"[ERROR] {error}")


# ─── START ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set! Please set the environment variable.")
    else:
        bot.run(TOKEN)
