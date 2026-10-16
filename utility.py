"""Infos, Hilfe, Umfragen, AFK, Sag/Embed."""
import discord
from discord.ext import commands

from utils import SERVER_NAME, BotError, embed, fmt_duration

NUM = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class Utility(commands.Cog, name="Utility"):
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store

    # ---------------------------------------------------------------- AFK
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        afk = self.store.guild(message.guild.id)["afk"]
        uid = str(message.author.id)
        if uid in afk and not message.content.lower().startswith("!afk"):
            afk.pop(uid)
            self.store.touch()
            await message.channel.send(f"👋 Willkommen zurück {message.author.mention}! Dein AFK-Status wurde beendet.", delete_after=8)
        for m in message.mentions:
            if str(m.id) in afk and m.id != message.author.id:
                await message.channel.send(f"💤 **{m.display_name}** ist AFK: {afk[str(m.id)]}", delete_after=10)

    @commands.hybrid_command(name="afk", description="Setze dich auf AFK")
    async def afk(self, ctx, *, grund: str = "Bin gleich zurück"):
        self.store.guild(ctx.guild.id)["afk"][str(ctx.author.id)] = grund[:150]
        self.store.touch()
        await ctx.send(f"💤 {ctx.author.mention} ist jetzt AFK: {grund[:150]}", allowed_mentions=discord.AllowedMentions.none())

    # --------------------------------------------------------------- Infos
    @commands.hybrid_command(name="hilfe", aliases=["help", "befehle"], description="Alle Befehle anzeigen")
    async def hilfe(self, ctx):
        e = embed(f"💙 {SERVER_NAME} – Hilfe", "Alle Befehle gehen mit **!** und mit **/**")
        e.add_field(name="🛡️ Moderation", inline=False, value=(
            "`!kick` `!ban` `!unban` `!timeout` `!untimeout` `!warn` `!warnungen` `!warnungenloeschen`\n"
            "`!clear` `!slowmode` `!lock` `!unlock` `!nick` `!rollegeben` `!rollenehmen`\n"
            "`!automod` – Automod anzeigen/einstellen (`!automod setzen`, `!automod wort`)"))
        e.add_field(name="📞 Calls", inline=False, value=(
            "Betrete **➕ Call erstellen** oder nutze `!call [name]`\n"
            "`!call umbenennen` `limit` `sperren` `entsperren` `verstecken` `zeigen` `einladen` `kick` "
            "`blockieren` `freigeben` `uebergeben` `uebernehmen` `info`"))
        e.add_field(name="🎫 Tickets", inline=False, value="`!ticket setup` `!ticket log` `!ticket hinzufuegen` `!ticket entfernen` `!ticket schliessen`")
        e.add_field(name="📈 Level & 💰 Wirtschaft", inline=False, value=(
            "`!rank` `!top` `!levelrolle` `!levelsystem`\n`!taeglich` `!arbeiten` `!konto` `!zocken` `!geben` `!reichste`"))
        e.add_field(name="🎉 Unterhaltung", inline=False, value=(
            "`!witz` `!8ball` `!wuerfel` `!muenze` `!schnickschnackschnuck` `!ship` `!wahrheit` `!pflicht` `!fakt`\n"
            "`!roast` `!kompliment` `!umarmen` `!hauen` `!bewerte` `!waehle` `!umdrehen` `!schlumpf` `!tictactoe`"))
        e.add_field(name="🧰 Nützliches", inline=False, value=(
            "`!umfrage` `!giveaway` `!erinnere` `!afk` `!sag` `!embed` `!ping` `!botinfo` `!serverinfo` `!userinfo` `!avatar`"))
        e.add_field(name="⚙️ Setup (Admin)", inline=False, value=(
            "`!setwillkommen` `!setgoodbye` `!setlog` `!setautorolle` `!willkommentext` `!willkommentest`\n"
            "`!reaktionsrolle` `!call setup` `!einstellungen`"))
        await ctx.send(embed=e)

    @commands.hybrid_command(name="ping", description="Latenz des Bots")
    async def ping(self, ctx):
        await ctx.send(f"🏓 Pong! `{round(self.bot.latency * 1000)} ms`")

    @commands.hybrid_command(name="botinfo", description="Infos über den Bot")
    async def botinfo(self, ctx):
        up = fmt_duration((discord.utils.utcnow() - self.bot.start_time).total_seconds())
        e = embed(f"🤖 {self.bot.user.name}")
        e.add_field(name="Server", value=len(self.bot.guilds))
        e.add_field(name="Nutzer", value=sum(g.member_count or 0 for g in self.bot.guilds))
        e.add_field(name="Laufzeit", value=up)
        e.add_field(name="Ping", value=f"{round(self.bot.latency * 1000)} ms")
        e.add_field(name="discord.py", value=discord.__version__)
        e.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="serverinfo", description="Infos zum Server")
    async def serverinfo(self, ctx):
        g = ctx.guild
        e = embed(f"📊 {g.name}")
        e.add_field(name="Mitglieder", value=g.member_count)
        e.add_field(name="Kanäle", value=len(g.channels))
        e.add_field(name="Rollen", value=len(g.roles))
        e.add_field(name="Boosts", value=g.premium_subscription_count)
        e.add_field(name="Besitzer", value=f"<@{g.owner_id}>")
        e.add_field(name="Erstellt", value=discord.utils.format_dt(g.created_at, "D"))
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="userinfo", aliases=["whois"], description="Infos zu einem Mitglied")
    async def userinfo(self, ctx, mitglied: discord.Member = None):
        m = mitglied or ctx.author
        roles = [r.mention for r in reversed(m.roles) if r != ctx.guild.default_role][:10]
        e = embed(f"👤 {m.display_name}")
        e.add_field(name="Name", value=str(m))
        e.add_field(name="ID", value=m.id)
        e.add_field(name="Account erstellt", value=discord.utils.format_dt(m.created_at, "D"))
        e.add_field(name="Beigetreten", value=discord.utils.format_dt(m.joined_at, "D") if m.joined_at else "?")
        e.add_field(name="Rollen", value=" ".join(roles) or "—", inline=False)
        e.set_thumbnail(url=m.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="avatar", description="Profilbild anzeigen")
    async def avatar(self, ctx, mitglied: discord.Member = None):
        m = mitglied or ctx.author
        e = embed(f"🖼️ Avatar von {m.display_name}")
        e.set_image(url=m.display_avatar.url)
        await ctx.send(embed=e)

    # ------------------------------------------------------------ Werkzeuge
    @commands.hybrid_command(name="umfrage", aliases=["poll"], description="Umfrage: Frage | Option1 | Option2 ...")
    async def umfrage(self, ctx, *, text: str):
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) == 1:
            frage, opts, emojis = parts[0], ["Ja", "Nein"], ["👍", "👎"]
            desc = f"**{frage}**"
        elif 3 <= len(parts) <= 11:
            frage, opts = parts[0], parts[1:]
            emojis = NUM[:len(opts)]
            desc = f"**{frage}**\n\n" + "\n".join(f"{emojis[i]} {o}" for i, o in enumerate(opts))
        else:
            raise BotError("Nutzung: `!umfrage Frage | Option1 | Option2 | …` (2–10 Optionen) oder nur eine Frage für Ja/Nein.")
        msg = await ctx.channel.send(embed=embed("📊 Umfrage", desc))
        for em in emojis:
            await msg.add_reaction(em)
        await ctx.send("✅ Umfrage erstellt.", ephemeral=True, delete_after=3)

    @commands.hybrid_command(name="sag", description="Lass den Bot etwas sagen")
    @commands.has_permissions(manage_messages=True)
    async def sag(self, ctx, *, text: str):
        if ctx.interaction:
            await ctx.send("✅ Gesendet.", ephemeral=True)
        else:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        await ctx.channel.send(text)

    @commands.hybrid_command(name="embed", description="Embed senden: Titel | Text")
    @commands.has_permissions(manage_messages=True)
    async def embed_cmd(self, ctx, *, text: str):
        if "|" not in text:
            raise BotError("Nutzung: `!embed Titel | Text`")
        title, desc = (p.strip() for p in text.split("|", 1))
        if ctx.interaction:
            await ctx.send("✅ Gesendet.", ephemeral=True)
        else:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        await ctx.channel.send(embed=embed(title[:250], desc[:4000]))


async def setup(bot):
    await bot.add_cog(Utility(bot))
