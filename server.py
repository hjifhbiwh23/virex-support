"""Willkommen, Verlassen, Auto-Rolle, Logs, Reaktionsrollen, Einstellungen."""
import discord
from discord.ext import commands

from utils import GREEN, RED, SERVER_NAME, YELLOW, BotError, embed, find_channel, send_log

DEFAULT_WELCOME = ("Hey {user}, schön dass du da bist!\n\n"
                   "Du bist Mitglied **#{count}**.\n"
                   "Lies dir die Regeln durch und hab ordentlich Spaß! 💙")


class Server(commands.Cog, name="Server"):
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store

    def g(self, guild):
        return self.store.guild(guild.id)

    # ------------------------------------------------------------ Events
    async def send_welcome(self, member: discord.Member):
        g = self.g(member.guild)
        ch = find_channel(self.store, member.guild, "welcome_channel", ["willkommen", "welcome"])
        if not ch:
            return
        text = (g["welcome_text"] or DEFAULT_WELCOME)
        text = (text.replace("{user}", member.mention).replace("{server}", member.guild.name)
                .replace("{count}", str(member.guild.member_count)))
        e = embed(f"👋 Willkommen bei {SERVER_NAME}!", text)
        e.add_field(name="Account erstellt", value=discord.utils.format_dt(member.created_at, "R"))
        e.set_thumbnail(url=member.display_avatar.url)
        await ch.send(content=member.mention, embed=e)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        g = self.g(member.guild)
        if g["auto_role"] and not member.bot:
            role = member.guild.get_role(g["auto_role"])
            if role:
                try:
                    await member.add_roles(role, reason="Auto-Rolle")
                except discord.HTTPException:
                    pass
        await self.send_welcome(member)
        await send_log(self.store, member.guild, embed("📥 Mitglied beigetreten", f"{member} ({member.id})", GREEN))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        ch = find_channel(self.store, member.guild, "goodbye_channel", ["verlassen", "goodbye", "tschüss", "tschuess"])
        if ch:
            await ch.send(embed=embed("👋 Tschüss!", f"**{member.display_name}** hat den Server verlassen.", RED))
        await send_log(self.store, member.guild, embed("📤 Mitglied gegangen", f"{member} ({member.id})", RED))

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.content:
            return
        await send_log(self.store, message.guild, embed(
            "🗑️ Nachricht gelöscht",
            f"**Von:** {message.author.mention}\n**Kanal:** {message.channel.mention}\n\n{message.content[:1500]}", YELLOW))

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        await send_log(self.store, before.guild, embed(
            "✏️ Nachricht bearbeitet",
            f"**Von:** {before.author.mention} in {before.channel.mention}\n"
            f"**Vorher:** {before.content[:700]}\n**Nachher:** {after.content[:700]}\n[Zur Nachricht]({after.jump_url})", YELLOW))

    # ---------------------------------------------- Reaktionsrollen (Events)
    async def _reaction_role(self, payload: discord.RawReactionActionEvent, add: bool):
        if not payload.guild_id or payload.user_id == self.bot.user.id:
            return
        rid = self.store.guild(payload.guild_id)["reaction_roles"].get(f"{payload.message_id}:{payload.emoji}")
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(rid) if (guild and rid) else None
        member = guild.get_member(payload.user_id) if guild else None
        if not role or not member:
            return
        try:
            await (member.add_roles(role) if add else member.remove_roles(role))
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self._reaction_role(payload, True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self._reaction_role(payload, False)

    # ------------------------------------------------------------ Setup
    @commands.hybrid_command(name="setwillkommen", description="Willkommen-Kanal festlegen")
    @commands.has_permissions(administrator=True)
    async def setwillkommen(self, ctx, kanal: discord.TextChannel):
        self.g(ctx.guild)["welcome_channel"] = kanal.id
        self.store.save()
        await ctx.send(f"✅ Willkommen-Kanal: {kanal.mention}")

    @commands.hybrid_command(name="setgoodbye", description="Verlassen-Kanal festlegen")
    @commands.has_permissions(administrator=True)
    async def setgoodbye(self, ctx, kanal: discord.TextChannel):
        self.g(ctx.guild)["goodbye_channel"] = kanal.id
        self.store.save()
        await ctx.send(f"✅ Verlassen-Kanal: {kanal.mention}")

    @commands.hybrid_command(name="setlog", description="Mod-Log-Kanal festlegen")
    @commands.has_permissions(administrator=True)
    async def setlog(self, ctx, kanal: discord.TextChannel):
        self.g(ctx.guild)["log_channel"] = kanal.id
        self.store.save()
        await ctx.send(f"✅ Log-Kanal: {kanal.mention}")

    @commands.hybrid_command(name="setautorolle", description="Rolle für neue Mitglieder festlegen")
    @commands.has_permissions(administrator=True)
    async def setautorolle(self, ctx, rolle: discord.Role):
        if rolle >= ctx.guild.me.top_role:
            raise BotError("Diese Rolle liegt über meiner. Schiebe meine Rolle weiter nach oben.")
        self.g(ctx.guild)["auto_role"] = rolle.id
        self.store.save()
        await ctx.send(f"✅ Auto-Rolle: {rolle.mention}")

    @commands.hybrid_command(name="willkommentext",
                             description="Eigener Willkommenstext ({user} {server} {count})")
    @commands.has_permissions(administrator=True)
    async def willkommentext(self, ctx, *, text: str):
        self.g(ctx.guild)["welcome_text"] = text
        self.store.save()
        await ctx.send("✅ Willkommenstext gespeichert. Teste ihn mit `!willkommentest`.")

    @commands.hybrid_command(name="willkommentest", description="Willkommensnachricht testen")
    @commands.has_permissions(administrator=True)
    async def willkommentest(self, ctx):
        await self.send_welcome(ctx.author)
        await ctx.send("✅ Test gesendet.", ephemeral=True)

    @commands.hybrid_command(name="einstellungen", description="Aktuelle Bot-Einstellungen anzeigen")
    @commands.has_permissions(administrator=True)
    async def einstellungen(self, ctx):
        g = self.g(ctx.guild)

        def ch(i):
            return f"<#{i}>" if i else "—"
        e = embed("⚙️ Einstellungen")
        e.add_field(name="Willkommen", value=ch(g["welcome_channel"]))
        e.add_field(name="Verlassen", value=ch(g["goodbye_channel"]))
        e.add_field(name="Mod-Log", value=ch(g["log_channel"]))
        e.add_field(name="Auto-Rolle", value=f"<@&{g['auto_role']}>" if g["auto_role"] else "—")
        e.add_field(name="Call-Hub", value=ch(g["call_hub"]))
        e.add_field(name="Ticket-Kategorie", value=ch(g["ticket_category"]))
        e.add_field(name="Level-System", value="an" if g["levels_on"] else "aus")
        e.add_field(name="Automod", value=", ".join(k for k, v in g["automod"].items() if v) or "aus", inline=False)
        await ctx.send(embed=e, ephemeral=True)

    # ----------------------------------------------------- Reaktionsrollen
    @commands.hybrid_command(name="reaktionsrolle",
                             description="Reaktionsrolle für eine Nachricht (in diesem Kanal) anlegen")
    @commands.has_permissions(administrator=True)
    async def reaktionsrolle(self, ctx, nachricht_id: str, emoji: str, rolle: discord.Role):
        if rolle >= ctx.guild.me.top_role:
            raise BotError("Diese Rolle liegt über meiner.")
        try:
            msg = await ctx.channel.fetch_message(int(nachricht_id))
        except (ValueError, discord.NotFound):
            raise BotError("Nachricht in diesem Kanal nicht gefunden. Nutze den Befehl im selben Kanal.")
        try:
            await msg.add_reaction(emoji)
        except discord.HTTPException:
            raise BotError("Dieses Emoji kann ich nicht verwenden.")
        self.g(ctx.guild)["reaction_roles"][f"{msg.id}:{emoji}"] = rolle.id
        self.store.save()
        await ctx.send(f"✅ Wer mit {emoji} reagiert, bekommt {rolle.mention}.")

    @commands.hybrid_command(name="reaktionsrolle_entfernen", description="Reaktionsrolle löschen")
    @commands.has_permissions(administrator=True)
    async def reaktionsrolle_entfernen(self, ctx, nachricht_id: str, emoji: str):
        if self.g(ctx.guild)["reaction_roles"].pop(f"{nachricht_id}:{emoji}", None) is None:
            raise BotError("Diese Reaktionsrolle gibt es nicht.")
        self.store.save()
        await ctx.send("✅ Reaktionsrolle entfernt.")


async def setup(bot):
    await bot.add_cog(Server(bot))
