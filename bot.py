import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import re
import random
from datetime import datetime, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PREFIX = "$"
SILENT_PREFIX = "*"

BAN_REQUEST_CHANNEL_ID = 1504101352475725945
STAFF_ROLE_NAME = "T Staff"
APPROVE_CHANNEL_ID = 1504531328731709540
POST_CHANNEL_ID = 1502194708993146921

CHANGELOG_CHANNEL_ID = 1504869572082274345
CUSTOMER_ROLE_NAME = "customer"

# ─── NEW CONFIG ───────────────────────────────────────────────────────────────
# Channel where deleted messages (word filter hits) are logged
MESSAGE_LOG_CHANNEL_ID = 0  # <-- SET YOUR LOG CHANNEL ID HERE

# Optional: URL to fetch live status JSON from your website
# Expected format: { "products": { "Rust": "Undetected", "Fortnite": "Updating", ... } }
# Set to None to disable live fetching
STATUS_API_URL = None  # e.g. "https://virexx.cc/api/status"

# Words that trigger the filter (lowercase, partial match)
BLACKLISTED_WORDS = [
    "spoof", "spoofed", "spoofer",
    "cheat", "cheats", "cheating",
    "hack", "hacked", "hacking",
    "aimbot", "wallhack", "esp",
]

# ─── DEFAULT PRODUCT STATUS ───────────────────────────────────────────────────
# Status options: "Undetected", "Updating", "Testing", "Detected", "Offline"
product_status: dict[str, str] = {
    "Apex Legends":     "Testing",
    "ARC Raiders":      "Updating",
    "DayZ":             "Updating",
    "Dead by Daylight": "Undetected",
    "Delta Force":      "Updating",
    "EFT":              "Updating",
    "Fortnite":         "Undetected",
    "HWID Virtualizer": "Testing",
    "PUBG":             "Updating",
    "R6X Lite":         "Undetected",
    "R6X":              "Undetected",
    "Rust":             "Undetected",
}

STATUS_COLORS = {
    "Undetected": 0x57F287,   # green
    "Updating":   0x5865F2,   # blue
    "Testing":    0xFEE75C,   # yellow
    "Detected":   0xED4245,   # red
    "Offline":    0x95A5A6,   # grey
}

STATUS_DOTS = {
    "Undetected": "🟢",
    "Updating":   "🔵",
    "Testing":    "🟡",
    "Detected":   "🔴",
    "Offline":    "⚫",
}

STATUS_OPTIONS = ["Undetected", "Updating", "Testing", "Detected", "Offline"]

# ─── BOT SETUP ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None
)

# ─── GIVEAWAY STORAGE ─────────────────────────────────────────────────────────
active_giveaways: dict = {}

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def has_staff_role(user: discord.Member) -> bool:
    role_names = [r.name.lower() for r in user.roles]
    return STAFF_ROLE_NAME.lower() in role_names


def parse_duration(duration_str: str) -> int | None:
    match = re.fullmatch(r"(\d+)([smhd])", duration_str.strip().lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return value * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def build_giveaway_embed(prize, winners, host_id, ends_at, entries) -> discord.Embed:
    embed = discord.Embed(
        title=f"🎉 GIVEAWAY — {prize}",
        description=(
            f"Click **🎉 Enter** to participate!\n\n"
            f"🏆 **Winners:** {winners}\n"
            f"👥 **Entries:** {entries}\n"
            f"🕐 **Ends:** <t:{int(ends_at.timestamp())}:R>\n"
            f"👑 **Hosted by:** <@{host_id}>"
        ),
        color=0xFF73FA
    )
    embed.set_footer(text=f"Ends on {ends_at.strftime('%d.%m.%Y at %H:%M')} UTC")
    return embed


def build_status_embed() -> discord.Embed:
    """Build the product status embed from current product_status dict."""
    embed = discord.Embed(
        title="📊 Current Product Status",
        color=0x6f2cff,
        timestamp=datetime.utcnow()
    )

    items = list(product_status.items())
    col_size = (len(items) + 2) // 3  # 3 columns

    for col_idx in range(3):
        chunk = items[col_idx * col_size:(col_idx + 1) * col_size]
        if not chunk:
            continue
        field_value = ""
        for name, status in chunk:
            dot = STATUS_DOTS.get(status, "⚫")
            field_value += f"{dot} **{name}**\n`{status}`\n\n"
        embed.add_field(name="\u200b", value=field_value.strip(), inline=True)

    embed.set_footer(text="Last updated")
    return embed


async def staff_check(ctx) -> bool:
    if not has_staff_role(ctx.author):
        embed = discord.Embed(
            title="❌ No Permission",
            description="You need at least the **T Staff** role to use this command.",
            color=0xFF4444
        )
        await ctx.send(embed=embed, delete_after=5)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        return False
    return True


def contains_blacklisted_word(content: str) -> str | None:
    """Returns the matched blacklisted word, or None."""
    lower = content.lower()
    for word in BLACKLISTED_WORDS:
        if word in lower:
            return word
    return None


async def log_deleted_message(message: discord.Message, matched_word: str):
    """Send a log embed to the message log channel."""
    log_channel = bot.get_channel(MESSAGE_LOG_CHANNEL_ID)
    if not log_channel:
        return

    embed = discord.Embed(
        title="🚫 Message Deleted — Word Filter",
        color=0xFF4444,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="👤 User", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
    embed.add_field(name="📍 Channel", value=message.channel.mention, inline=True)
    embed.add_field(name="🔍 Matched Word", value=f"`{matched_word}`", inline=True)
    embed.add_field(name="💬 Message Content", value=f"```{message.content[:1000]}```", inline=False)
    embed.set_footer(text=f"User ID: {message.author.id}")
    await log_channel.send(embed=embed)


async def end_giveaway(message_id: int):
    if message_id not in active_giveaways:
        return

    data = active_giveaways.pop(message_id)
    channel = bot.get_channel(data["channel_id"])
    if not channel:
        return

    try:
        msg = await channel.fetch_message(message_id)
    except discord.NotFound:
        return

    entries = list(data["entries"])
    prize = data["prize"]
    winner_count = min(data["winners"], len(entries))

    embed = discord.Embed(title=f"🎉 GIVEAWAY ENDED — {prize}", color=0x888888)

    if not entries:
        embed.description = "❌ Nobody entered. No winner was drawn."
        await msg.edit(embed=embed, view=None)
        await channel.send("❌ The giveaway ended with no participants.")
        return

    winners = random.sample(entries, winner_count)
    winner_mentions = " ".join(f"<@{w}>" for w in winners)

    embed.description = (
        f"**Prize:** {prize}\n"
        f"**Winner(s):** {winner_mentions}\n"
        f"👑 **Hosted by:** <@{data['host_id']}>"
    )
    embed.set_footer(text="Giveaway ended")

    await msg.edit(embed=embed, view=None)
    await channel.send(f"🎉 Congratulations {winner_mentions}! You won **{prize}**!")


# ─── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="virex.gg | $manual"))
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Silent prefix
    if message.content.startswith(SILENT_PREFIX):
        if not has_staff_role(message.author):
            return
        content = message.content[len(SILENT_PREFIX):].strip()
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        if content:
            await message.channel.send(content)
        return

    # ─── WORD FILTER ──────────────────────────────────────────────────────────
    # Skip filter for staff members
    if not has_staff_role(message.author):
        matched = contains_blacklisted_word(message.content)
        if matched:
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            # Warn the user
            warn_embed = discord.Embed(
                title="⚠️ Message Removed",
                description=(
                    f"{message.author.mention}, one or more words in your message are **not allowed** in this server.\n\n"
                    "**Examples of how to rephrase:**\n"
                    "• cheat → chair\n"
                    "• spoof → woof\n"
                    "• spoofer → woofer\n"
                    "• hack → h4ck"
                ),
                color=0x6f2cff
            )
            warn_embed.set_footer(text="Virex — Word Filter")
            try:
                await message.channel.send(
                    content=message.author.mention,
                    embed=warn_embed,
                    delete_after=10
                )
            except discord.Forbidden:
                pass

            # Log to message log channel
            await log_deleted_message(message, matched)
            return

    await bot.process_commands(message)


# ─── PREFIX COMMANDS ──────────────────────────────────────────────────────────
@bot.command(name="commands")
async def commands_list(ctx):
    if not await staff_check(ctx):
        return
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    embed = discord.Embed(title="📋 Virex Bot — Command List", color=0x6f2cff)
    embed.add_field(
        name="📌 Prefix Commands (`$`)",
        value=(
            "`$commands` — Shows this command list\n"
            "`$manual` — AnyDesk manual guide\n"
            "`$activate` — Windows activation guide\n"
            "`$tempvsperm` — Temp vs Perm Woofer info\n"
            "`$proof` — Purchase proof instructions\n"
            "`$ban <user_id> <reason>` — Send a ban request\n"
            "`$scam` — Post a scam warning (@everyone)\n"
            "`$anydesk` — AnyDesk setup guide"
        ),
        inline=False
    )
    embed.add_field(
        name="⚡ Slash Commands (`/`)",
        value=(
            "`/post <link>` — Submit a video for approval\n"
            "`/changelog <game> <update>` — Post a game update\n"
            "`/giveaway <duration> <winners> <prize>` — Start a giveaway\n"
            "`/gend <message_id>` — End a giveaway immediately\n"
            "`/greroll <channel> <message_id>` — Reroll a giveaway winner\n"
            "`/status` — Show current product status\n"
            "`/setstatus <product> <status>` — Manually update a product's status"
        ),
        inline=False
    )
    embed.add_field(
        name="🔇 Silent Prefix (`*`)",
        value="`*<text>` — Send a message anonymously (deletes your original)",
        inline=False
    )
    embed.set_footer(text="All commands require the T Staff role • Virex Team")
    await ctx.send(embed=embed)


@bot.command(name="manual")
async def manual(ctx):
    if not await staff_check(ctx):
        return
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(title="📖 AnyDesk Manual — Virex", color=0x5865F2)
    embed.add_field(
        name="💰 Perm Guide Assistance",
        value=(
            "For **€20** you can hire a Staff member *(NOT Trial Staff)* "
            "to perform the Perm Guide for you via **AnyDesk**."
        ),
        inline=False
    )
    embed.add_field(name="⚠️ Note", value="This is different from the ASUS Manual.", inline=False)
    embed.set_footer(text="Virex Team")
    await ctx.send(embed=embed)


@bot.command(name="activate")
async def activate(ctx):
    if not await staff_check(ctx):
        return
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(
        title="🪟 Windows Activation Guide",
        description="Follow the steps below to activate Windows.",
        color=0x00B4D8
    )
    embed.add_field(name="1️⃣ Open PowerShell as Administrator", value="Press Windows → type `PowerShell` → Run as Administrator", inline=False)
    embed.add_field(name="2️⃣ Run this command", value="```irm https://get.activated.win/ | iex```", inline=False)
    embed.add_field(name="3️⃣ Press `4`", value="​", inline=True)
    embed.add_field(name="4️⃣ Activate Windows → `1`", value="​", inline=True)
    embed.add_field(name="5️⃣ Auto-Renewal → `5`", value="​", inline=True)
    embed.set_footer(text="Virex Team")
    await ctx.send(embed=embed)


@bot.command(name="tempvsperm")
async def tempvsperm(ctx):
    if not await staff_check(ctx):
        return
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(title="🐾 Temp vs Perm Woofer", color=0xF4A261)
    embed.add_field(
        name="🔒 Permanent Woofer",
        value="- Permanent serial changes\n- Requires Windows reinstall\n- Long-term security",
        inline=False
    )
    embed.add_field(
        name="⏳ Temporary Woofer",
        value="- Lasts one session\n- Resets after restart\n- No reinstall needed",
        inline=False
    )
    embed.set_footer(text="Virex Team")
    await ctx.send(embed=embed)


@bot.command(name="proof")
async def proof(ctx):
    if not await staff_check(ctx):
        return
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(
        title="📸 Submit Purchase Proof",
        description="Follow the instructions below carefully.",
        color=0x2ECC71
    )
    embed.add_field(name="📧 Email Confirmation", value="- Screenshot your confirmation email\n- Amount & date must be visible", inline=False)
    embed.add_field(name="💳 Payment Proof", value="- Screenshot PayPal/Crypto transaction\n- Amount & recipient visible", inline=False)
    embed.add_field(name="⚠️ Important", value="Fake screenshots = permanent ban.", inline=False)
    embed.set_footer(text="Virex Team")
    await ctx.send(embed=embed)


@bot.command(name="ban")
async def ban_request(ctx, user_id: str = None, *, reason: str = None):
    if not await staff_check(ctx):
        return
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    if not user_id or not reason:
        embed = discord.Embed(title="❌ Incorrect Usage", description="Usage: `$ban <user_id> <reason>`", color=0xFF4444)
        await ctx.send(embed=embed, delete_after=5)
        return
    try:
        target_user = await bot.fetch_user(int(user_id))
        user_display = f"{target_user} (`{user_id}`)"
        avatar = target_user.display_avatar.url
    except Exception:
        user_display = f"Unknown User (`{user_id}`)"
        avatar = None

    embed = discord.Embed(title="🔨 Ban Request", color=0xFF0000)
    embed.add_field(name="👤 User", value=user_display, inline=False)
    embed.add_field(name="🛡️ Requested By", value=f"{ctx.author}", inline=False)
    embed.add_field(name="📝 Reason", value=reason, inline=False)
    if avatar:
        embed.set_thumbnail(url=avatar)
    embed.set_footer(text=f"User ID: {user_id}")

    ban_channel = bot.get_channel(BAN_REQUEST_CHANNEL_ID)
    if ban_channel:
        await ban_channel.send(embed=embed)
        confirm = discord.Embed(title="✅ Ban Request Sent", description=f"Request sent to {ban_channel.mention}", color=0x00FF00)
        await ctx.send(embed=confirm, delete_after=5)
    else:
        await ctx.send("❌ Ban request channel not found.", delete_after=5)


@bot.command(name="scam")
async def scam(ctx):
    if not await staff_check(ctx):
        return
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(
        title="🚨 SCAM WARNING – PLEASE READ! 🚨",
        description=(
            "We've had reports of people sending DMs claiming that "
            "**'Virex is a scam'** or **'detected'**.\n\n"
            "⚠️ This is happening across multiple servers.\n\n"
            "👉 What you should do:\n"
            "🚫 Do NOT buy anything from them\n"
            "🔒 Block the user\n"
            "📸 Take screenshots\n"
            "🎟️ Open a support ticket"
        ),
        color=0x6f2cff
    )
    embed.set_image(url="https://i.imgur.com/t1JeHvA.png")
    embed.set_footer(text="Virex Team")
    await ctx.send(content="@everyone @here", embed=embed)


@bot.command(name="anydesk")
async def anydesk(ctx):
    if not await staff_check(ctx):
        return
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(
        title="🖥️ AnyDesk Setup Guide",
        description=(
            "**Step 1: Download AnyDesk**\n"
            "[Click here and install.](https://anydesk.com/en/downloads)\n\n"
            "**Step 2: Run AnyDesk**\n"
            "Open the .exe file, sync date & time if errors occur.\n\n"
            "**Step 3: Provide Your ID**\n"
            "Copy your AnyDesk ID into your Discord ticket.\n\n"
            "**Step 4: Grant Full Permissions**\n"
            "Wait for staff to connect, then grant full access."
        ),
        color=0x2F3136
    )
    embed.set_footer(text="Virex Team")
    await ctx.send(embed=embed)


# ─── APPROVE VIEW ─────────────────────────────────────────────────────────────
class ApproveView(discord.ui.View):
    def __init__(self, link: str, author: discord.Member):
        super().__init__(timeout=300)
        self.link = link
        self.author = author

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_staff_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to approve posts.", ephemeral=True)
            return
        post_channel = bot.get_channel(POST_CHANNEL_ID)
        if not post_channel:
            await interaction.response.send_message("❌ Post channel not found.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🎬 New Video Posted",
            description=(f"{self.link}\n\nMake sure to like and comment on the video.\nSubscribe for more content."),
            color=0x2F3136
        )
        embed.set_footer(text=f"Posted by {self.author}")
        await post_channel.send(content="@everyone", embed=embed)
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message("✅ Post approved and sent.", ephemeral=True)

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_staff_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to deny posts.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message("🚫 Post denied.", ephemeral=True)


# ─── SLASH COMMANDS ───────────────────────────────────────────────────────────
@bot.tree.command(name="post", description="Submit a video for approval")
@app_commands.describe(link="Video link to submit")
async def post(interaction: discord.Interaction, link: str):
    if not has_staff_role(interaction.user):
        await interaction.response.send_message("❌ You need the **T Staff** role to use this command.", ephemeral=True)
        return
    approve_channel = bot.get_channel(APPROVE_CHANNEL_ID)
    if not approve_channel:
        await interaction.response.send_message("❌ Approval channel not found. Contact an admin.", ephemeral=True)
        return
    embed = discord.Embed(
        title="📬 New Post Request",
        description=(f"**User:** {interaction.user.mention}\n**Link:** {link}"),
        color=0xffcc00
    )
    embed.set_footer(text=f"Submitted by {interaction.user}")
    await approve_channel.send(embed=embed, view=ApproveView(link, interaction.user))
    await interaction.response.send_message("✅ Your post has been submitted for approval.", ephemeral=True)


@bot.tree.command(name="changelog", description="Post a game update to the changelog channel")
@app_commands.describe(game="Name of the game that was updated", update="Description of what changed")
async def changelog(interaction: discord.Interaction, game: str, update: str):
    if not has_staff_role(interaction.user):
        await interaction.response.send_message("❌ You need the **T Staff** role to use this command.", ephemeral=True)
        return
    changelog_channel = bot.get_channel(CHANGELOG_CHANNEL_ID)
    if not changelog_channel:
        await interaction.response.send_message("❌ Changelog channel not found.", ephemeral=True)
        return
    customer_role = discord.utils.find(lambda r: r.name.lower() == CUSTOMER_ROLE_NAME.lower(), interaction.guild.roles)
    embed = discord.Embed(title=f"🔄 {game} — Update", description=update, color=0x6f2cff)
    embed.set_footer(text=f"Posted by {interaction.user} • Virex Team")
    ping_content = customer_role.mention if customer_role else f"@{CUSTOMER_ROLE_NAME}"
    await changelog_channel.send(content=ping_content, embed=embed)
    await interaction.response.send_message(f"✅ Changelog for **{game}** has been posted!", ephemeral=True)


# ─── STATUS COMMANDS ──────────────────────────────────────────────────────────
@bot.tree.command(name="status", description="Show the current product status")
async def status(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    # Optional: Fetch live status from website API
    if STATUS_API_URL:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(STATUS_API_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "products" in data and isinstance(data["products"], dict):
                            for name, st in data["products"].items():
                                if name in product_status:
                                    product_status[name] = st
        except Exception as e:
            print(f"[Status API] Failed to fetch: {e}")

    embed = build_status_embed()
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="setstatus", description="Manually set a product's status")
@app_commands.describe(
    product="Product name (e.g. Rust, Fortnite)",
    new_status="New status to set"
)
@app_commands.choices(new_status=[
    app_commands.Choice(name="🟢 Undetected", value="Undetected"),
    app_commands.Choice(name="🔵 Updating",   value="Updating"),
    app_commands.Choice(name="🟡 Testing",    value="Testing"),
    app_commands.Choice(name="🔴 Detected",   value="Detected"),
    app_commands.Choice(name="⚫ Offline",    value="Offline"),
])
async def setstatus(interaction: discord.Interaction, product: str, new_status: str):
    if not has_staff_role(interaction.user):
        await interaction.response.send_message(
            "❌ You need the **T Staff** role to change product status.",
            ephemeral=True
        )
        return

    # Case-insensitive product lookup
    matched_product = None
    for key in product_status.keys():
        if key.lower() == product.lower():
            matched_product = key
            break

    if matched_product is None:
        product_list = "\n".join(f"• {p}" for p in product_status.keys())
        await interaction.response.send_message(
            f"❌ Product **{product}** not found.\n\n**Available products:**\n{product_list}",
            ephemeral=True
        )
        return

    old_status = product_status[matched_product]
    product_status[matched_product] = new_status

    dot = STATUS_DOTS.get(new_status, "⚫")
    embed = discord.Embed(
        title="✅ Status Updated",
        description=(
            f"**Product:** {matched_product}\n"
            f"**Old Status:** {STATUS_DOTS.get(old_status, '⚫')} {old_status}\n"
            f"**New Status:** {dot} {new_status}"
        ),
        color=STATUS_COLORS.get(new_status, 0x888888)
    )
    embed.set_footer(text=f"Updated by {interaction.user} • Virex Team")
    await interaction.response.send_message(embed=embed)


# ─── GIVEAWAY VIEW ────────────────────────────────────────────────────────────
class GiveawayView(discord.ui.View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="🎉 Enter", style=discord.ButtonStyle.primary, custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.message_id not in active_giveaways:
            await interaction.response.send_message("❌ This giveaway has already ended.", ephemeral=True)
            return
        data = active_giveaways[self.message_id]
        user_id = interaction.user.id
        if user_id in data["entries"]:
            data["entries"].discard(user_id)
            await interaction.response.send_message("✅ You have **left** the giveaway.", ephemeral=True)
        else:
            data["entries"].add(user_id)
            await interaction.response.send_message(f"🎉 You are now entered in the giveaway for **{data['prize']}**!", ephemeral=True)
        try:
            embed = build_giveaway_embed(data["prize"], data["winners"], data["host_id"], data["ends_at"], len(data["entries"]))
            await interaction.message.edit(embed=embed)
        except Exception:
            pass


# ─── GIVEAWAY SLASH COMMANDS ──────────────────────────────────────────────────
@bot.tree.command(name="giveaway", description="Start a giveaway")
@app_commands.describe(duration="Duration e.g. 10m, 2h, 1d", winners="Number of winners", prize="What is being given away?")
async def giveaway_start(interaction: discord.Interaction, duration: str, winners: int, prize: str):
    if not has_staff_role(interaction.user):
        await interaction.response.send_message("❌ You need the **T Staff** role to start a giveaway.", ephemeral=True)
        return
    seconds = parse_duration(duration)
    if not seconds:
        await interaction.response.send_message("❌ Invalid duration. Examples: `10s`, `5m`, `2h`, `1d`", ephemeral=True)
        return
    if winners < 1:
        await interaction.response.send_message("❌ At least 1 winner required.", ephemeral=True)
        return
    ends_at = datetime.utcnow() + timedelta(seconds=seconds)
    embed = build_giveaway_embed(prize, winners, interaction.user.id, ends_at, 0)
    await interaction.response.send_message("✅ Starting giveaway...", ephemeral=True)
    msg = await interaction.channel.send(content="@everyone", embed=embed)
    active_giveaways[msg.id] = {
        "channel_id": interaction.channel.id,
        "prize": prize,
        "winners": winners,
        "host_id": interaction.user.id,
        "ends_at": ends_at,
        "entries": set()
    }
    view = GiveawayView(msg.id)
    await msg.edit(view=view)
    asyncio.create_task(_giveaway_timer(msg.id, seconds))


async def _giveaway_timer(message_id: int, seconds: int):
    await asyncio.sleep(seconds)
    await end_giveaway(message_id)


@bot.tree.command(name="gend", description="End a giveaway immediately (by message ID)")
@app_commands.describe(message_id="The message ID of the giveaway embed")
async def giveaway_end(interaction: discord.Interaction, message_id: str):
    if not has_staff_role(interaction.user):
        await interaction.response.send_message("❌ You need the **T Staff** role.", ephemeral=True)
        return
    try:
        mid = int(message_id)
    except ValueError:
        await interaction.response.send_message("❌ Invalid message ID.", ephemeral=True)
        return
    if mid not in active_giveaways:
        await interaction.response.send_message("❌ No active giveaway found with that ID.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Ending giveaway...", ephemeral=True)
    await end_giveaway(mid)


@bot.tree.command(name="greroll", description="Reroll a winner from a giveaway embed")
@app_commands.describe(channel="The channel where the giveaway was held", message_id="The message ID of the giveaway embed")
async def giveaway_reroll(interaction: discord.Interaction, channel: discord.TextChannel, message_id: str):
    if not has_staff_role(interaction.user):
        await interaction.response.send_message("❌ You need the **T Staff** role.", ephemeral=True)
        return
    try:
        mid = int(message_id)
    except ValueError:
        await interaction.response.send_message("❌ Invalid message ID.", ephemeral=True)
        return
    if mid not in active_giveaways:
        await interaction.response.send_message(
            "❌ Giveaway not found in memory. Reroll only works if the bot hasn't restarted since the giveaway ended.",
            ephemeral=True
        )
        return
    entries = list(active_giveaways[mid]["entries"])
    prize = active_giveaways[mid]["prize"]
    if not entries:
        await interaction.response.send_message("❌ No entries to reroll from.", ephemeral=True)
        return
    new_winner = random.choice(entries)
    try:
        await channel.fetch_message(mid)
    except discord.NotFound:
        await interaction.response.send_message("❌ Message not found in that channel.", ephemeral=True)
        return
    await channel.send(f"🔁 Reroll! The new winner of **{prize}** is <@{new_winner}>! Congratulations!")
    await interaction.response.send_message(f"✅ Rerolled! New winner: <@{new_winner}>", ephemeral=True)


# ─── ERROR HANDLING ───────────────────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing arguments.", delete_after=5)
        return
    print(f"[ERROR] {error}")


# ─── START ────────────────────────────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    print("❌ DISCORD_TOKEN environment variable not found.")
else:
    bot.run(TOKEN)
