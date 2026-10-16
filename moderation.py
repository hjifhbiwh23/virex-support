"""Moderation + Automod."""
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Literal

import discord
from discord.ext import commands

from utils import (GREEN, RED, YELLOW, BotError, can_moderate, embed, fmt_duration,
                   parse_duration, send_log)

SPAM_LIMIT, SPAM_SECONDS, SPAM_TIMEOUT_MIN = 6, 6, 2
INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\w+", re.I)


class Moderation(commands.Cog, name="Moderation"):
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store
        self.spam = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))

    def g(self, guild):
        return self.store.guild(guild.id)

    async def done(self, ctx, title, text, color):
        await ctx.send(embed=embed(title, text, color))
        le = embed(title, text, color)
        le.add_field(name="Moderator", value=ctx.author.mention)
        await send_log(self.store, ctx.guild, le)

    # ----------------------------------------------------------- Automod
    async def _block(self, message: discord.Message, text: str):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await message.channel.send(f"{message.author.mention} {text}", delete_after=6)
        await send_log(self.store, message.guild, embed(
            "🤖 Automod", f"{message.author.mention} in {message.channel.mention}: {text}\n> {message.content[:500]}", YELLOW))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return
        if message.author.guild_permissions.manage_messages:
            return
        g = self.g(message.guild)
        am, content = g["automod"], message.content

        if am["woerter"] and g["badwords"]:
            low = content.lower()
            if any(re.search(rf"\b{re.escape(w)}\b", low) for w in g["badwords"]):
                return await self._block(message, "Achte bitte auf deine Wortwahl! 🚫")
        if am["einladungen"] and INVITE_RE.search(content):
            return await self._block(message, "Einladungen zu anderen Servern sind hier nicht erlaubt! 🚫")
        if am["erwaehnungen"] and len(message.mentions) + len(message.role_mentions) >= 5:
            return await self._block(message, "Bitte nicht so viele Leute auf einmal erwähnen! 🚫")
        if am["caps"]:
            letters = [c for c in content if c.isalpha()]
            if len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
                return await self._block(message, "Bitte nicht so viel Capslock! 🚫")
        if am["spam"]:
            q = self.spam[(message.guild.id, message.author.id)]
            now = time.time()
            q.append(now)
            if len(q) == SPAM_LIMIT and now - q[0] < SPAM_SECONDS:
                q.clear()
                try:
                    await message.author.timeout(timedelta(minutes=SPAM_TIMEOUT_MIN), reason="Automod: Spam")
                except discord.HTTPException:
                    return
                await message.channel.send(
                    f"{message.author.mention} wurde wegen Spam für {SPAM_TIMEOUT_MIN} Min stummgeschaltet. 🤐",
                    delete_after=10)
                await send_log(self.store, message.guild, embed(
                    "🤖 Automod: Spam", f"{message.author.mention} → Timeout {SPAM_TIMEOUT_MIN} Min", YELLOW))

    @commands.hybrid_group(name="automod", fallback="status", invoke_without_command=True,
                           description="Automod-Status anzeigen")
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx):
        am = self.g(ctx.guild)["automod"]
        lines = [f"{'✅' if v else '❌'} **{k}**" for k, v in am.items()]
        lines.append(f"\nSchimpfwörter in der Liste: **{len(self.g(ctx.guild)['badwords'])}**")
        lines.append("Ändern: `!automod setzen <funktion> <an|aus>`")
        await ctx.send(embed=embed("🤖 Automod", "\n".join(lines)))

    @automod.command(name="setzen", description="Automod-Funktion an- oder ausschalten")
    @commands.has_permissions(manage_guild=True)
    async def automod_setzen(self, ctx, funktion: Literal["einladungen", "spam", "caps", "erwaehnungen", "woerter"],
                             status: Literal["an", "aus"]):
        self.g(ctx.guild)["automod"][funktion] = status == "an"
        self.store.save()
        await ctx.send(f"✅ Automod **{funktion}**: {status}")

    @automod.command(name="wort", description="Wort zur Schimpfwortliste hinzufügen")
    @commands.has_permissions(manage_guild=True)
    async def automod_wort(self, ctx, *, wort: str):
        words = self.g(ctx.guild)["badwords"]
        if wort.lower() not in words:
            words.append(wort.lower())
            self.store.save()
        await ctx.send("✅ Hinzugefügt.", ephemeral=True)
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

    @automod.command(name="wortentfernen", description="Wort aus der Schimpfwortliste entfernen")
    @commands.has_permissions(manage_guild=True)
    async def automod_wortentfernen(self, ctx, *, wort: str):
        words = self.g(ctx.guild)["badwords"]
        if wort.lower() not in words:
            raise BotError("Das Wort steht nicht in der Liste.")
        words.remove(wort.lower())
        self.store.save()
        await ctx.send("✅ Entfernt.", ephemeral=True)

    @automod.command(name="woerter", description="Schimpfwortliste anzeigen")
    @commands.has_permissions(manage_guild=True)
    async def automod_woerter(self, ctx):
        words = self.g(ctx.guild)["badwords"]
        await ctx.send("||" + (", ".join(words) or "Die Liste ist leer.") + "||", ephemeral=True)

    # -------------------------------------------------------- Moderation
    @commands.hybrid_command(name="kick", description="Mitglied kicken")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, mitglied: discord.Member, *, grund: str = "Kein Grund angegeben"):
        can_moderate(ctx, mitglied)
        await mitglied.kick(reason=f"{ctx.author}: {grund}")
        await self.done(ctx, "👢 Kick", f"**{mitglied}** wurde gekickt.\n**Grund:** {grund}", YELLOW)

    @commands.hybrid_command(name="ban", description="Nutzer bannen (auch per ID)")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, nutzer: discord.User, *, grund: str = "Kein Grund angegeben"):
        member = ctx.guild.get_member(nutzer.id)
        if member:
            can_moderate(ctx, member)
        await ctx.guild.ban(nutzer, reason=f"{ctx.author}: {grund}", delete_message_days=0)
        await self.done(ctx, "🔨 Ban", f"**{nutzer}** wurde gebannt.\n**Grund:** {grund}", RED)

    @commands.hybrid_command(name="unban", description="Nutzer per ID entbannen")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, nutzer_id: str):
        try:
            user = await self.bot.fetch_user(int(nutzer_id))
            await ctx.guild.unban(user)
        except (ValueError, discord.NotFound):
            raise BotError("Nutzer nicht gefunden oder nicht gebannt.")
        await self.done(ctx, "✅ Unban", f"**{user}** wurde entbannt.", GREEN)

    @commands.hybrid_command(name="timeout", aliases=["mute"], description="Mitglied stummschalten (z.B. 10m, 2h, 1d)")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx, mitglied: discord.Member, dauer: str, *, grund: str = "Kein Grund angegeben"):
        can_moderate(ctx, mitglied)
        secs = parse_duration(dauer)
        if not secs or secs > 28 * 86400:
            raise BotError("Ungültige Dauer. Beispiele: `10m`, `2h`, `1d` (maximal 28 Tage).")
        await mitglied.timeout(timedelta(seconds=secs), reason=f"{ctx.author}: {grund}")
        await self.done(ctx, "🤐 Timeout",
                        f"{mitglied.mention} für **{fmt_duration(secs)}** stummgeschaltet.\n**Grund:** {grund}", YELLOW)

    @commands.hybrid_command(name="untimeout", aliases=["unmute"], description="Timeout aufheben")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx, mitglied: discord.Member):
        await mitglied.timeout(None)
        await self.done(ctx, "🔊 Timeout aufgehoben", f"{mitglied.mention} darf wieder schreiben.", GREEN)

    @commands.hybrid_command(name="warn", description="Mitglied verwarnen (3 Warns = 1 Std Timeout)")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx, mitglied: discord.Member, *, grund: str):
        can_moderate(ctx, mitglied)
        warns = self.g(ctx.guild)["warns"].setdefault(str(mitglied.id), [])
        warns.append({"grund": grund, "mod": ctx.author.id, "zeit": discord.utils.utcnow().strftime("%d.%m.%Y %H:%M")})
        self.store.save()
        extra = ""
        if len(warns) == 3:
            try:
                await mitglied.timeout(timedelta(hours=1), reason="3 Verwarnungen")
                extra = "\n🤐 **3 Verwarnungen** → 1 Stunde Timeout."
            except discord.HTTPException:
                pass
        await self.done(ctx, "⚠️ Verwarnung",
                        f"{mitglied.mention} wurde verwarnt.\n**Grund:** {grund}\n**Verwarnungen:** {len(warns)}{extra}", YELLOW)
        try:
            await mitglied.send(f"⚠️ Du wurdest auf **{ctx.guild.name}** verwarnt: {grund}")
        except discord.HTTPException:
            pass

    @commands.hybrid_command(name="warnungen", aliases=["warns"], description="Verwarnungen eines Mitglieds anzeigen")
    @commands.has_permissions(moderate_members=True)
    async def warnungen(self, ctx, mitglied: discord.Member):
        warns = self.g(ctx.guild)["warns"].get(str(mitglied.id), [])
        if not warns:
            return await ctx.send(f"✅ {mitglied.display_name} hat keine Verwarnungen.")
        lines = [f"**{i}.** {w['grund']} – <@{w['mod']}> ({w['zeit']})" for i, w in enumerate(warns, 1)]
        await ctx.send(embed=embed(f"⚠️ Verwarnungen von {mitglied.display_name}", "\n".join(lines)[:4000]))

    @commands.hybrid_command(name="warnungenloeschen", description="Alle Verwarnungen eines Mitglieds löschen")
    @commands.has_permissions(moderate_members=True)
    async def warnungenloeschen(self, ctx, mitglied: discord.Member):
        self.g(ctx.guild)["warns"].pop(str(mitglied.id), None)
        self.store.save()
        await ctx.send(f"✅ Verwarnungen von {mitglied.mention} gelöscht.")

    @commands.hybrid_command(name="clear", aliases=["purge"], description="Nachrichten löschen (optional nur von einem Mitglied)")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx, anzahl: commands.Range[int, 1, 100], mitglied: discord.Member = None):
        await ctx.defer(ephemeral=True)
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        check = (lambda m: m.author == mitglied) if mitglied else None
        deleted = await ctx.channel.purge(limit=anzahl, check=check)
        await ctx.send(f"🧹 {len(deleted)} Nachrichten gelöscht.", delete_after=5)

    @commands.hybrid_command(name="slowmode", description="Slowmode setzen (0 = aus)")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx, sekunden: commands.Range[int, 0, 21600]):
        await ctx.channel.edit(slowmode_delay=sekunden)
        await ctx.send("🐇 Slowmode ausgeschaltet." if sekunden == 0 else f"🐢 Slowmode: {sekunden} Sekunden.")

    @commands.hybrid_command(name="lock", description="Kanal sperren")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🔒 Kanal gesperrt.")

    @commands.hybrid_command(name="unlock", description="Kanal entsperren")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
        await ctx.send("🔓 Kanal entsperrt.")

    @commands.hybrid_command(name="nick", description="Nickname eines Mitglieds ändern (leer = zurücksetzen)")
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nick(self, ctx, mitglied: discord.Member, *, name: str = None):
        can_moderate(ctx, mitglied)
        await mitglied.edit(nick=name[:32] if name else None)
        await ctx.send(f"✅ Nickname von {mitglied.mention} geändert.")

    def _check_role(self, ctx, rolle: discord.Role):
        if rolle >= ctx.guild.me.top_role or (ctx.author.id != ctx.guild.owner_id and rolle >= ctx.author.top_role):
            raise BotError("Diese Rolle liegt über deiner oder meiner höchsten Rolle.")

    @commands.hybrid_command(name="rollegeben", description="Mitglied eine Rolle geben")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rollegeben(self, ctx, mitglied: discord.Member, rolle: discord.Role):
        self._check_role(ctx, rolle)
        await mitglied.add_roles(rolle, reason=str(ctx.author))
        await ctx.send(f"✅ {mitglied.mention} hat jetzt {rolle.mention}.", allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="rollenehmen", description="Mitglied eine Rolle entziehen")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rollenehmen(self, ctx, mitglied: discord.Member, rolle: discord.Role):
        self._check_role(ctx, rolle)
        await mitglied.remove_roles(rolle, reason=str(ctx.author))
        await ctx.send(f"✅ {mitglied.mention} hat {rolle.mention} nicht mehr.", allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(Moderation(bot))
