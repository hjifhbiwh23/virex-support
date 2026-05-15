import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PREFIX = "$"
SILENT_PREFIX = "*"

BAN_REQUEST_CHANNEL_ID = 1504101352475725945
STAFF_ROLE_NAME = "T Staff"
APPROVE_CHANNEL_ID = 1504531328731709540
POST_CHANNEL_ID = 1502194708993146921

# ─── NEU: Changelog Konfiguration ────────────────────────────────────────────
CHANGELOG_CHANNEL_ID = 1504869572082274345  # <-- HIER deine Changelog-Channel-ID eintragen
CUSTOMER_ROLE_NAME = "customer"              # <-- Rollenname anpassen falls nötig

# ─── BOT SETUP ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None
)

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def has_staff_role(member: discord.Member) -> bool:
    role_names = [r.name.lower() for r in member.roles]
    return STAFF_ROLE_NAME.lower() in role_names

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
        except:
            pass

        return False

    return True

# ─── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(
        activity=discord.Game(name="virex.gg | $manual")
    )
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.content.startswith(SILENT_PREFIX):
        if not has_staff_role(message.author):
            return

        content = message.content[len(SILENT_PREFIX):].strip()

        try:
            await message.delete()
        except:
            pass

        if content:
            await message.channel.send(content)

        return

    await bot.process_commands(message)

# ─── COMMANDS ─────────────────────────────────────────────────────────────────

@bot.command(name="manual")
async def manual(ctx):
    if not await staff_check(ctx):
        return

    await ctx.message.delete()

    embed = discord.Embed(
        title="📖 AnyDesk Manual — Virex",
        color=0x5865F2
    )

    embed.add_field(
        name="💰 Perm Guide Assistance",
        value=(
            "For **€20** you can hire a Staff member *(NOT Trial Staff)* "
            "to perform the Perm Guide for you via **AnyDesk**."
        ),
        inline=False
    )

    embed.add_field(
        name="⚠️ Note",
        value="This is different from the ASUS Manual.",
        inline=False
    )

    embed.set_footer(text="Virex Team")

    await ctx.send(embed=embed)

@bot.command(name="activate")
async def activate(ctx):
    if not await staff_check(ctx):
        return

    await ctx.message.delete()

    embed = discord.Embed(
        title="🪟 Windows Activation Guide",
        description="Follow the steps below to activate Windows.",
        color=0x00B4D8
    )

    embed.add_field(
        name="1️⃣ Open PowerShell as Administrator",
        value="Press Windows → type `PowerShell` → Run as Administrator",
        inline=False
    )

    embed.add_field(
        name="2️⃣ Run this command",
        value="```irm https://get.activated.win/ | iex```",
        inline=False
    )

    embed.add_field(name="3️⃣ Press `4`", value="​", inline=True)
    embed.add_field(name="4️⃣ Activate Windows → `1`", value="​", inline=True)
    embed.add_field(name="5️⃣ Auto-Renewal → `5`", value="​", inline=True)

    embed.set_footer(text="Virex Team")

    await ctx.send(embed=embed)

@bot.command(name="tempvsperm")
async def tempvsperm(ctx):
    if not await staff_check(ctx):
        return

    await ctx.message.delete()

    embed = discord.Embed(
        title="🐾 Temp vs Perm Woofer",
        color=0xF4A261
    )

    embed.add_field(
        name="🔒 Permanent Woofer",
        value=(
            "- Permanent serial changes\n"
            "- Requires Windows reinstall\n"
            "- Long-term security"
        ),
        inline=False
    )

    embed.add_field(
        name="⏳ Temporary Woofer",
        value=(
            "- Lasts one session\n"
            "- Resets after restart\n"
            "- No reinstall needed"
        ),
        inline=False
    )

    embed.set_footer(text="Virex Team")

    await ctx.send(embed=embed)

@bot.command(name="proof")
async def proof(ctx):
    if not await staff_check(ctx):
        return

    await ctx.message.delete()

    embed = discord.Embed(
        title="📸 Submit Purchase Proof",
        description="Follow the instructions below carefully.",
        color=0x2ECC71
    )

    embed.add_field(
        name="📧 Email Confirmation",
        value=(
            "- Screenshot your confirmation email\n"
            "- Amount & date must be visible"
        ),
        inline=False
    )

    embed.add_field(
        name="💳 Payment Proof",
        value=(
            "- Screenshot PayPal/Crypto transaction\n"
            "- Amount & recipient visible"
        ),
        inline=False
    )

    embed.add_field(
        name="⚠️ Important",
        value="Fake screenshots = permanent ban.",
        inline=False
    )

    embed.set_footer(text="Virex Team")

    await ctx.send(embed=embed)

@bot.command(name="ban")
async def ban_request(ctx, user_id: str = None, *, reason: str = None):

    if not await staff_check(ctx):
        return

    await ctx.message.delete()

    if not user_id or not reason:
        embed = discord.Embed(
            title="❌ Incorrect Usage",
            description="Usage: `$ban <user_id> <reason>`",
            color=0xFF4444
        )
        await ctx.send(embed=embed, delete_after=5)
        return

    try:
        target_user = await bot.fetch_user(int(user_id))
        user_display = f"{target_user} (`{user_id}`)"
        avatar = target_user.display_avatar.url
    except Exception:
        user_display = f"Unknown User (`{user_id}`)"
        avatar = None

    embed = discord.Embed(
        title="🔨 Ban Request",
        color=0xFF0000
    )

    embed.add_field(name="👤 User", value=user_display, inline=False)
    embed.add_field(name="🛡️ Requested By", value=f"{ctx.author}", inline=False)
    embed.add_field(name="📝 Reason", value=reason, inline=False)

    if avatar:
        embed.set_thumbnail(url=avatar)

    embed.set_footer(text=f"User ID: {user_id}")

    ban_channel = bot.get_channel(BAN_REQUEST_CHANNEL_ID)

    if ban_channel:
        await ban_channel.send(embed=embed)
        confirm = discord.Embed(
            title="✅ Ban Request Sent",
            description=f"Request sent to {ban_channel.mention}",
            color=0x00FF00
        )
        await ctx.send(embed=confirm, delete_after=5)

@bot.command(name="scam")
async def scam(ctx):

    if not await staff_check(ctx):
        return

    await ctx.message.delete()

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

    await ctx.message.delete()

    embed = discord.Embed(
        title="🖥️ AnyDesk Setup Guide",
        description=(
            "**Step 1: Download AnyDesk**\n"
            "[Click here and install.](https://anydesk.com/en/downloads)\n\n"
            "**Step 2: Run AnyDesk**\n"
            "Open the .exe file, sync date & time if errors.\n\n"
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
    def __init__(self, link: str, author: discord.User):
        super().__init__(timeout=300)
        self.link = link
        self.author = author

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not has_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to approve posts.",
                ephemeral=True
            )
            return

        post_channel = bot.get_channel(POST_CHANNEL_ID)

        if not post_channel:
            await interaction.response.send_message(
                "❌ Post channel not found.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎬 New Video Posted",
            description=(
                f"{self.link}\n\n"
                "Make sure to like and comment on the video.\n"
                "Subscribe for more content."
            ),
            color=0x2F3136
        )

        embed.set_footer(text=f"Posted by {self.author}")

        await post_channel.send(embed=embed)

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.response.send_message(
            "✅ Post approved and sent.",
            ephemeral=True
        )

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not has_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to deny posts.",
                ephemeral=True
            )
            return

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.response.send_message(
            "🚫 Post denied.",
            ephemeral=True
        )


# ─── SLASH COMMANDS ───────────────────────────────────────────────────────────

# /post — NUR für Staff (FIX)
@bot.tree.command(name="post", description="Submit a video for approval")
@app_commands.describe(link="Video link to submit")
async def post(interaction: discord.Interaction, link: str):

    # FIX: Nur Staff darf /post nutzen
    if not has_staff_role(interaction.user):
        await interaction.response.send_message(
            "❌ You need the **T Staff** role to use this command.",
            ephemeral=True
        )
        return

    approve_channel = bot.get_channel(APPROVE_CHANNEL_ID)

    if not approve_channel:
        await interaction.response.send_message(
            "❌ Approval channel not found. Contact an admin.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="📬 New Post Request",
        description=(
            f"**User:** {interaction.user.mention}\n"
            f"**Link:** {link}"
        ),
        color=0xffcc00
    )

    embed.set_footer(text=f"Submitted by {interaction.user}")

    await approve_channel.send(
        embed=embed,
        view=ApproveView(link, interaction.user)
    )

    await interaction.response.send_message(
        "✅ Your post has been sent for approval.",
        ephemeral=True
    )


# ─── NEU: /changelog ──────────────────────────────────────────────────────────
@bot.tree.command(name="changelog", description="Post a game update to the changelog channel")
@app_commands.describe(
    game="Name of the game that was updated",
    update="Description of the update / what changed"
)
async def changelog(interaction: discord.Interaction, game: str, update: str):

    # Nur Staff darf Changelogs posten
    if not has_staff_role(interaction.user):
        await interaction.response.send_message(
            "❌ You need the **T Staff** role to use this command.",
            ephemeral=True
        )
        return

    changelog_channel = bot.get_channel(CHANGELOG_CHANNEL_ID)

    if not changelog_channel:
        await interaction.response.send_message(
            "❌ Changelog channel not found. Check `CHANGELOG_CHANNEL_ID` in the config.",
            ephemeral=True
        )
        return

    # Customer-Rolle für den Ping suchen
    customer_role = discord.utils.find(
        lambda r: r.name.lower() == CUSTOMER_ROLE_NAME.lower(),
        interaction.guild.roles
    )

    embed = discord.Embed(
        title=f"🔄 {game} — Update",
        description=update,
        color=0x6f2cff
    )

    embed.set_footer(text=f"Posted by {interaction.user} • Virex Team")

    # Ping-Text vorbereiten
    ping_content = customer_role.mention if customer_role else "@customer"

    await changelog_channel.send(content=ping_content, embed=embed)

    await interaction.response.send_message(
        f"✅ Changelog für **{game}** wurde gepostet!",
        ephemeral=True
    )


# ─── ERRORS ───────────────────────────────────────────────────────────────────
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
    print("❌ DISCORD_TOKEN not found.")
else:
    bot.run(TOKEN)
