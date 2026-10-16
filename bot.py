"""
SCHLUMPF SKANDI – Discord Bot (Deutsch) – alles in einer Datei
Alle Befehle funktionieren mit  !befehl  UND  /befehl  (Hybrid-Commands).
Start:  python bot.py   (Token in der Umgebungsvariable DISCORD_TOKEN)
"""
import asyncio
import copy
import hashlib
import io
import json
import logging
import os
import random
import re
import signal
import time
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks


# ============================================================================
# UTILS
# ============================================================================
SERVER_NAME = "SCHLUMPF SKANDI"
EMBED_COLOR = 0x3BA7FF  # Schlumpf-Blau
GREEN, RED, YELLOW = 0x57F287, 0xED4245, 0xFEE75C
CURRENCY = "Schlumpfbeeren 🫐"

DATA_DIR = Path(os.getenv("DATA_DIR", "."))  # Auf Railway: Volume nach /data mounten
DATA_FILE = DATA_DIR / "data.json"
log = logging.getLogger("schlumpf")


class BotError(commands.CommandError):
    """Fehler, dessen Text direkt dem Nutzer angezeigt wird."""


def embed(title: str, desc: str = "", color: int = EMBED_COLOR) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_footer(text=SERVER_NAME)
    return e


GUILD_DEFAULTS = {
    "welcome_channel": None, "goodbye_channel": None, "log_channel": None,
    "auto_role": None, "welcome_text": None,
    "warns": {},
    "automod": {"einladungen": True, "spam": True, "caps": False,
                "erwaehnungen": True, "woerter": True},
    "badwords": [],
    "call_hub": None, "calls": {},
    "ticket_category": None, "ticket_role": None, "ticket_log": None,
    "levels_on": True, "levels": {}, "level_roles": {},
    "eco": {}, "reaction_roles": {}, "giveaways": {}, "afk": {},
}


class Store:
    """Einfacher JSON-Speicher. touch() = später speichern, save() = sofort speichern."""

    def __init__(self):
        self.data = {"guilds": {}, "reminders": []}
        self.dirty = False
        self.load()

    def load(self):
        try:
            if DATA_FILE.exists():
                self.data.update(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        except Exception as e:
            log.error("Konnte data.json nicht laden: %s", e)

    def save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = DATA_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(DATA_FILE)
            self.dirty = False
        except Exception as e:
            log.error("Konnte data.json nicht speichern: %s", e)

    def touch(self):
        self.dirty = True

    def flush(self):
        if self.dirty:
            self.save()

    def guild(self, gid: int) -> dict:
        g = self.data["guilds"].setdefault(str(gid), {})
        for k, v in GUILD_DEFAULTS.items():
            if k not in g:
                g[k] = copy.deepcopy(v)
        for k, v in GUILD_DEFAULTS["automod"].items():
            g["automod"].setdefault(k, v)
        return g


def find_channel(store: Store, guild: discord.Guild, key: str, names: list):
    cid = store.guild(guild.id).get(key)
    if cid:
        ch = guild.get_channel(cid)
        if ch:
            return ch
    for ch in guild.text_channels:
        if any(n in ch.name.lower() for n in names):
            return ch
    return None


async def send_log(store: Store, guild: discord.Guild, e: discord.Embed):
    cid = store.guild(guild.id).get("log_channel")
    ch = guild.get_channel(cid) if cid else None
    if ch:
        try:
            await ch.send(embed=e)
        except discord.HTTPException:
            pass


def can_moderate(ctx, target: discord.Member):
    """Wirft BotError, wenn die Aktion gegen target nicht erlaubt ist."""
    if target.id == ctx.author.id:
        raise BotError("Das kannst du nicht bei dir selbst machen. 😅")
    if target.id == ctx.bot.user.id:
        raise BotError("Ich mache doch nichts gegen mich selbst. 🤖")
    if target.id == ctx.guild.owner_id:
        raise BotError("Der Serverbesitzer ist tabu.")
    if ctx.author.id != ctx.guild.owner_id and target.top_role >= ctx.author.top_role:
        raise BotError("Dieses Mitglied hat eine gleich hohe oder höhere Rolle als du.")
    if target.top_role >= ctx.guild.me.top_role:
        raise BotError("Dieses Mitglied hat eine höhere Rolle als ich. Schiebe meine Rolle weiter nach oben.")


_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_DUR = r"(\d+)\s*([smhdw])"


def parse_duration(text: str):
    """'10m', '2h30m', '1d' -> Sekunden (oder None bei ungültiger Eingabe)."""
    text = text.lower().strip()
    parts = re.findall(_DUR, text)
    if not parts or re.sub(_DUR + r"|\s", "", text):
        return None
    return sum(int(n) * _UNITS[u] for n, u in parts)


def fmt_duration(seconds: int) -> str:
    seconds = int(seconds)
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = [f"{d} Tg" if d else "", f"{h} Std" if h else "", f"{m} Min" if m else "",
             f"{s} Sek" if (s and not d and not h) else ""]
    return " ".join(p for p in parts if p) or "0 Sek"


# ============================================================================
# SERVER
# ============================================================================
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


# ============================================================================
# MODERATION
# ============================================================================
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


# ============================================================================
# CALLS
# ============================================================================
OWNER_PERMS = dict(view_channel=True, connect=True, speak=True, move_members=True, mute_members=True)


class Calls(commands.Cog, name="Calls"):
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store

    def g(self, guild):
        return self.store.guild(guild.id)

    # ------------------------------------------------------ Hilfsfunktionen
    async def create_call(self, member: discord.Member, name: str = None):
        """Erstellt einen Call. Gibt (Kanal, neu_erstellt) zurück."""
        guild, g = member.guild, self.g(member.guild)
        for cid, owner in g["calls"].items():
            if owner == member.id and (ch := guild.get_channel(int(cid))):
                return ch, False

        hub = guild.get_channel(g["call_hub"]) if g["call_hub"] else None
        category = hub.category if hub else None
        overwrites = dict(category.overwrites) if category else {}
        overwrites[member] = discord.PermissionOverwrite(**OWNER_PERMS)
        name = (name or f"📞 {member.display_name}s Call")[:100]
        try:
            ch = await guild.create_voice_channel(name, category=category, overwrites=overwrites,
                                                  reason=f"Call von {member}")
        except discord.Forbidden:
            ch = await guild.create_voice_channel(name, category=category, reason=f"Call von {member}")
        g["calls"][str(ch.id)] = member.id
        self.store.save()
        return ch, True

    async def remove_call(self, ch: discord.VoiceChannel):
        self.g(ch.guild)["calls"].pop(str(ch.id), None)
        self.store.save()
        try:
            await ch.delete(reason="Call leer")
        except discord.HTTPException:
            pass

    async def set_owner(self, ch: discord.VoiceChannel, new: discord.Member, old_id: int = None):
        self.g(ch.guild)["calls"][str(ch.id)] = new.id
        self.store.save()
        try:
            if old_id and (old := ch.guild.get_member(old_id)):
                await ch.set_permissions(old, overwrite=None)
            await ch.set_permissions(new, **OWNER_PERMS)
        except discord.HTTPException:
            pass

    async def cleanup_later(self, ch: discord.VoiceChannel, delay: int = 60):
        await asyncio.sleep(delay)
        ch = ch.guild.get_channel(ch.id)
        if ch and str(ch.id) in self.g(ch.guild)["calls"] and not [m for m in ch.members if not m.bot]:
            await self.remove_call(ch)

    def own_call(self, ctx, allow_admin: bool = True) -> discord.VoiceChannel:
        vs = ctx.author.voice
        if not vs or not vs.channel:
            raise BotError("Du musst dazu in deinem Call sein.")
        owner = self.g(ctx.guild)["calls"].get(str(vs.channel.id))
        if owner is None:
            raise BotError("Du bist in keinem Bot-Call.")
        if owner != ctx.author.id and not (allow_admin and ctx.author.guild_permissions.manage_channels):
            raise BotError("Das ist nicht dein Call.")
        return vs.channel

    # --------------------------------------------------------------- Events
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:  # nach Neustart verwaiste Calls aufräumen
            g = self.g(guild)
            for cid in list(g["calls"]):
                ch = guild.get_channel(int(cid))
                if ch is None:
                    g["calls"].pop(cid, None)
                elif not [m for m in ch.members if not m.bot]:
                    await self.remove_call(ch)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return
        g = self.g(member.guild)

        if after.channel and g["call_hub"] and after.channel.id == g["call_hub"] and not member.bot:
            try:
                ch, _ = await self.create_call(member)
                await member.move_to(ch)
            except discord.HTTPException as e:
                log.warning("Call konnte nicht erstellt werden: %s", e)

        old = before.channel
        if old and str(old.id) in g["calls"]:
            humans = [m for m in old.members if not m.bot]
            if not humans:
                await self.remove_call(old)
            elif g["calls"][str(old.id)] == member.id:
                new = random.choice(humans)
                await self.set_owner(old, new, member.id)
                try:
                    await old.send(f"👑 {new.mention} ist jetzt der Besitzer dieses Calls.")
                except discord.HTTPException:
                    pass

    # ------------------------------------------------------------- Befehle
    @commands.hybrid_group(name="call", fallback="neu", invoke_without_command=True,
                           description="Eigenen Call erstellen (optional mit Namen)")
    @commands.bot_has_permissions(manage_channels=True)
    async def call(self, ctx, *, name: str = None):
        ch, created = await self.create_call(ctx.author, name)
        if ctx.author.voice and ctx.author.voice.channel:
            if ctx.author.voice.channel != ch:
                try:
                    await ctx.author.move_to(ch)
                except discord.Forbidden:
                    raise BotError("Mir fehlt das Recht **Mitglieder verschieben**. Prüfe mit `!rechte`.")
            return await ctx.send(f"✅ Dein Call: {ch.mention}")
        if created:
            asyncio.create_task(self.cleanup_later(ch))
        await ctx.send(f"✅ Dein Call: {ch.mention} – komm rein! (Wird gelöscht, wenn niemand in 60 Sek. beitritt.)")

    @call.command(name="setup", description="Call-System einrichten (erstellt Kategorie + Hub)")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def call_setup(self, ctx):
        cat = await ctx.guild.create_category("📞 Calls")
        hub = await ctx.guild.create_voice_channel("➕ Call erstellen", category=cat)
        self.g(ctx.guild)["call_hub"] = hub.id
        self.store.save()
        await ctx.send(f"✅ Fertig! Wer {hub.mention} betritt, bekommt einen eigenen Call.\n"
                       "Verschiebe Kategorie/Hub gern an die gewünschte Stelle.")

    @call.command(name="hub", description="Vorhandenen Sprachkanal als Call-Hub festlegen")
    @commands.has_permissions(administrator=True)
    async def call_hub(self, ctx, kanal: discord.VoiceChannel):
        self.g(ctx.guild)["call_hub"] = kanal.id
        self.store.save()
        await ctx.send(f"✅ Call-Hub: {kanal.mention}")

    @call.command(name="umbenennen", description="Deinen Call umbenennen")
    async def call_umbenennen(self, ctx, *, name: str):
        ch = self.own_call(ctx)
        await ch.edit(name=name[:100])
        await ctx.send(f"✅ Call heißt jetzt **{name[:100]}**.")

    @call.command(name="limit", description="Nutzerlimit setzen (0 = unbegrenzt)")
    async def call_limit(self, ctx, anzahl: commands.Range[int, 0, 99]):
        await self.own_call(ctx).edit(user_limit=anzahl)
        await ctx.send("✅ Limit aufgehoben." if anzahl == 0 else f"✅ Limit: **{anzahl}** Personen.")

    @call.command(name="sperren", description="Call sperren (niemand Neues kann beitreten)")
    async def call_sperren(self, ctx):
        await self.own_call(ctx).set_permissions(ctx.guild.default_role, connect=False)
        await ctx.send("🔒 Dein Call ist gesperrt. Mit `!call einladen @user` lässt du Leute rein.")

    @call.command(name="entsperren", description="Call wieder öffnen")
    async def call_entsperren(self, ctx):
        await self.own_call(ctx).set_permissions(ctx.guild.default_role, connect=None)
        await ctx.send("🔓 Dein Call ist wieder offen.")

    @call.command(name="verstecken", description="Call für andere unsichtbar machen")
    async def call_verstecken(self, ctx):
        await self.own_call(ctx).set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.send("🙈 Dein Call ist jetzt versteckt.")

    @call.command(name="zeigen", description="Versteckten Call wieder sichtbar machen")
    async def call_zeigen(self, ctx):
        await self.own_call(ctx).set_permissions(ctx.guild.default_role, view_channel=None)
        await ctx.send("👀 Dein Call ist wieder sichtbar.")

    @call.command(name="einladen", description="Mitglied in deinen (gesperrten) Call einladen")
    async def call_einladen(self, ctx, mitglied: discord.Member):
        ch = self.own_call(ctx)
        await ch.set_permissions(mitglied, view_channel=True, connect=True)
        await ctx.send(f"✅ {mitglied.mention} darf jetzt in {ch.mention}.")

    @call.command(name="kick", description="Mitglied aus deinem Call werfen")
    async def call_kick(self, ctx, mitglied: discord.Member):
        ch = self.own_call(ctx)
        if mitglied.voice is None or mitglied.voice.channel != ch:
            raise BotError("Diese Person ist nicht in deinem Call.")
        if mitglied.id == ctx.author.id:
            raise BotError("Du kannst dich nicht selbst kicken.")
        await mitglied.move_to(None)
        await ctx.send(f"👢 {mitglied.display_name} wurde aus dem Call geworfen.")

    @call.command(name="blockieren", description="Mitglied dauerhaft aus deinem Call aussperren")
    async def call_blockieren(self, ctx, mitglied: discord.Member):
        ch = self.own_call(ctx)
        if mitglied.id == ctx.author.id:
            raise BotError("Du kannst dich nicht selbst blockieren.")
        await ch.set_permissions(mitglied, connect=False)
        if mitglied.voice and mitglied.voice.channel == ch:
            await mitglied.move_to(None)
        await ctx.send(f"⛔ {mitglied.display_name} kommt nicht mehr in diesen Call.")

    @call.command(name="freigeben", description="Blockierung eines Mitglieds aufheben")
    async def call_freigeben(self, ctx, mitglied: discord.Member):
        await self.own_call(ctx).set_permissions(mitglied, overwrite=None)
        await ctx.send(f"✅ {mitglied.display_name} darf wieder in den Call.")

    @call.command(name="uebergeben", description="Besitz deines Calls übergeben")
    async def call_uebergeben(self, ctx, mitglied: discord.Member):
        ch = self.own_call(ctx, allow_admin=False)
        if mitglied.voice is None or mitglied.voice.channel != ch or mitglied.bot:
            raise BotError("Die Person muss in deinem Call sein.")
        await self.set_owner(ch, mitglied, ctx.author.id)
        await ctx.send(f"👑 {mitglied.mention} ist jetzt Besitzer dieses Calls.")

    @call.command(name="uebernehmen", description="Call übernehmen, wenn der Besitzer weg ist")
    async def call_uebernehmen(self, ctx):
        vs = ctx.author.voice
        if not vs or not vs.channel:
            raise BotError("Du musst in einem Call sein.")
        ch, g = vs.channel, self.g(ctx.guild)
        owner_id = g["calls"].get(str(ch.id))
        if owner_id is None:
            raise BotError("Das ist kein Bot-Call.")
        if owner_id == ctx.author.id:
            raise BotError("Du bist schon der Besitzer.")
        if any(m.id == owner_id for m in ch.members):
            raise BotError("Der Besitzer ist noch im Call.")
        await self.set_owner(ch, ctx.author, owner_id)
        await ctx.send(f"👑 {ctx.author.mention} hat den Call übernommen.")

    @call.command(name="info", description="Infos zu deinem aktuellen Call")
    async def call_info(self, ctx):
        vs = ctx.author.voice
        if not vs or not vs.channel or str(vs.channel.id) not in self.g(ctx.guild)["calls"]:
            raise BotError("Du bist in keinem Bot-Call.")
        ch = vs.channel
        owner = self.g(ctx.guild)["calls"][str(ch.id)]
        ow = ch.overwrites_for(ctx.guild.default_role)
        e = embed(f"📞 {ch.name}")
        e.add_field(name="Besitzer", value=f"<@{owner}>")
        e.add_field(name="Personen", value=f"{len(ch.members)}" + (f"/{ch.user_limit}" if ch.user_limit else ""))
        e.add_field(name="Status", value="🔒 gesperrt" if ow.connect is False else "🔓 offen")
        e.add_field(name="Sichtbar", value="nein" if ow.view_channel is False else "ja")
        await ctx.send(embed=e)


# ============================================================================
# TICKETS
# ============================================================================
def ticket_owner(ch) -> int:
    if isinstance(ch, discord.TextChannel) and ch.topic and ch.topic.startswith("ticket:"):
        try:
            return int(ch.topic.split(":")[1])
        except ValueError:
            return 0
    return 0


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket erstellen", emoji="🎫", style=discord.ButtonStyle.primary,
                       custom_id="schlumpf:ticket_open")
    async def open_ticket(self, inter: discord.Interaction, button: discord.ui.Button):
        guild, store = inter.guild, inter.client.store
        g = store.guild(guild.id)
        for ch in guild.text_channels:
            if ticket_owner(ch) == inter.user.id:
                return await inter.response.send_message(f"Du hast schon ein Ticket: {ch.mention}", ephemeral=True)

        category = guild.get_channel(g["ticket_category"]) if g["ticket_category"] else None
        role = guild.get_role(g["ticket_role"]) if g["ticket_role"] else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                    attach_files=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                           read_message_history=True, manage_messages=True)
        slug = re.sub(r"[^a-z0-9]", "", inter.user.name.lower()) or str(inter.user.id)
        ch = await guild.create_text_channel(f"ticket-{slug}"[:90], category=category, overwrites=overwrites,
                                             topic=f"ticket:{inter.user.id}", reason=f"Ticket von {inter.user}")
        e = embed("🎫 Ticket", f"Hallo {inter.user.mention}! Beschreibe bitte dein Anliegen.\n"
                               "Das Team meldet sich so schnell wie möglich.")
        await ch.send(content=f"{inter.user.mention} {role.mention if role else ''}", embed=e, view=TicketControls(),
                      allowed_mentions=discord.AllowedMentions(users=True, roles=True))
        await inter.response.send_message(f"✅ Ticket erstellt: {ch.mention}", ephemeral=True)


class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket schließen", emoji="🔒", style=discord.ButtonStyle.danger,
                       custom_id="schlumpf:ticket_close")
    async def close_ticket(self, inter: discord.Interaction, button: discord.ui.Button):
        await close_ticket(inter.client, inter.channel, inter.user, inter)


async def close_ticket(bot, ch, user: discord.Member, inter: discord.Interaction = None, ctx=None):
    g = bot.store.guild(ch.guild.id)
    role = ch.guild.get_role(g["ticket_role"]) if g["ticket_role"] else None
    owner = ticket_owner(ch)
    if not owner:
        raise BotError("Das ist kein Ticket-Kanal.")
    if not (user.id == owner or user.guild_permissions.manage_channels or (role and role in user.roles)):
        if inter:
            return await inter.response.send_message("❌ Das darfst du nicht.", ephemeral=True)
        raise BotError("Das darfst du nicht.")

    text = "🔒 Ticket wird in 5 Sekunden geschlossen …"
    if inter:
        await inter.response.send_message(text)
    else:
        await ctx.send(text)

    lines = []
    async for m in ch.history(limit=1000, oldest_first=True):
        att = " ".join(a.url for a in m.attachments)
        lines.append(f"[{m.created_at:%d.%m.%Y %H:%M}] {m.author}: {m.content} {att}".rstrip())
    log_ch = (ch.guild.get_channel(g["ticket_log"]) if g["ticket_log"]
              else find_channel(bot.store, ch.guild, "log_channel", ["ticket-log", "logs"]))
    if log_ch:
        file = discord.File(io.BytesIO("\n".join(lines).encode("utf-8")), filename=f"{ch.name}.txt")
        try:
            await log_ch.send(embed=embed("🎫 Ticket geschlossen", f"**{ch.name}** von <@{owner}>\nGeschlossen von {user.mention}"),
                              file=file)
        except discord.HTTPException:
            pass
    await asyncio.sleep(5)
    await ch.delete(reason=f"Ticket geschlossen von {user}")


class Tickets(commands.Cog, name="Tickets"):
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store

    async def cog_load(self):
        self.bot.add_view(TicketPanel())
        self.bot.add_view(TicketControls())

    @commands.hybrid_group(name="ticket", fallback="info", invoke_without_command=True,
                           description="Ticket-System: Hilfe")
    async def ticket(self, ctx):
        await ctx.send(embed=embed("🎫 Tickets",
                                   "`!ticket setup [kategorie] [supportrolle]` – Panel im aktuellen Kanal erstellen\n"
                                   "`!ticket log #kanal` – Kanal für Transkripte\n"
                                   "`!ticket hinzufuegen @user` / `!ticket entfernen @user`\n"
                                   "`!ticket schliessen` – Ticket schließen"))

    @ticket.command(name="setup", description="Ticket-Panel in diesem Kanal erstellen")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def ticket_setup(self, ctx, kategorie: discord.CategoryChannel = None, supportrolle: discord.Role = None):
        g = self.store.guild(ctx.guild.id)
        if kategorie:
            g["ticket_category"] = kategorie.id
        if supportrolle:
            g["ticket_role"] = supportrolle.id
        self.store.save()
        e = embed("🎫 Support", "Du brauchst Hilfe oder hast eine Frage?\nKlicke unten auf den Button, um ein Ticket zu öffnen.")
        await ctx.channel.send(embed=e, view=TicketPanel())
        await ctx.send("✅ Ticket-Panel erstellt.", ephemeral=True)

    @ticket.command(name="log", description="Kanal für Ticket-Transkripte festlegen")
    @commands.has_permissions(administrator=True)
    async def ticket_log(self, ctx, kanal: discord.TextChannel):
        self.store.guild(ctx.guild.id)["ticket_log"] = kanal.id
        self.store.save()
        await ctx.send(f"✅ Transkripte landen in {kanal.mention}.")

    @ticket.command(name="hinzufuegen", description="Person zum Ticket hinzufügen")
    @commands.has_permissions(manage_channels=True)
    async def ticket_add(self, ctx, mitglied: discord.Member):
        if not ticket_owner(ctx.channel):
            raise BotError("Das ist kein Ticket-Kanal.")
        await ctx.channel.set_permissions(mitglied, view_channel=True, send_messages=True, read_message_history=True)
        await ctx.send(f"✅ {mitglied.mention} wurde hinzugefügt.")

    @ticket.command(name="entfernen", description="Person aus dem Ticket entfernen")
    @commands.has_permissions(manage_channels=True)
    async def ticket_remove(self, ctx, mitglied: discord.Member):
        if not ticket_owner(ctx.channel):
            raise BotError("Das ist kein Ticket-Kanal.")
        await ctx.channel.set_permissions(mitglied, overwrite=None)
        await ctx.send(f"✅ {mitglied.mention} wurde entfernt.")

    @ticket.command(name="schliessen", description="Dieses Ticket schließen")
    async def ticket_close(self, ctx):
        await close_ticket(self.bot, ctx.channel, ctx.author, ctx=ctx)


# ============================================================================
# LEVELS
# ============================================================================
def level_from_xp(xp: int) -> int:
    return int((xp / 100) ** 0.5)


def xp_for_level(level: int) -> int:
    return 100 * level * level


class Levels(commands.Cog, name="Levels"):
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store
        self.cooldown = {}

    def g(self, guild):
        return self.store.guild(guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or message.content.startswith("!"):
            return
        g = self.g(message.guild)
        if not g["levels_on"]:
            return
        key, now = (message.guild.id, message.author.id), time.time()
        if now - self.cooldown.get(key, 0) < 60:
            return
        self.cooldown[key] = now

        entry = g["levels"].setdefault(str(message.author.id), {"xp": 0})
        old = level_from_xp(entry["xp"])
        entry["xp"] += random.randint(15, 25)
        new = level_from_xp(entry["xp"])
        self.store.touch()
        if new > old:
            await message.channel.send(f"🎉 {message.author.mention} ist jetzt **Level {new}**! 💙")
            for lvl, rid in g["level_roles"].items():
                role = message.guild.get_role(rid)
                if role and int(lvl) <= new and role not in message.author.roles:
                    try:
                        await message.author.add_roles(role, reason="Level-Rolle")
                    except discord.HTTPException:
                        pass

    @commands.hybrid_command(name="rank", aliases=["level", "rang"], description="Dein Level und deine XP anzeigen")
    async def rank(self, ctx, mitglied: discord.Member = None):
        m = mitglied or ctx.author
        levels = self.g(ctx.guild)["levels"]
        xp = levels.get(str(m.id), {"xp": 0})["xp"]
        lvl = level_from_xp(xp)
        cur, nxt = xp_for_level(lvl), xp_for_level(lvl + 1)
        filled = int((xp - cur) / (nxt - cur) * 10)
        place = sorted(levels.values(), key=lambda v: v["xp"], reverse=True).index(levels[str(m.id)]) + 1 \
            if str(m.id) in levels else "–"
        e = embed(f"📈 {m.display_name}")
        e.add_field(name="Level", value=lvl)
        e.add_field(name="XP", value=f"{xp}")
        e.add_field(name="Platz", value=f"#{place}")
        e.add_field(name=f"Fortschritt zu Level {lvl + 1}",
                    value=f"{'🟦' * filled}{'⬜' * (10 - filled)}  {xp - cur}/{nxt - cur} XP", inline=False)
        e.set_thumbnail(url=m.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="top", aliases=["rangliste", "leaderboard"], description="Die Level-Rangliste")
    async def top(self, ctx):
        levels = self.g(ctx.guild)["levels"]
        ranking = sorted(levels.items(), key=lambda kv: kv[1]["xp"], reverse=True)[:10]
        if not ranking:
            raise BotError("Noch niemand hat XP gesammelt.")
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[i] if i < 3 else f'**{i + 1}.**'} <@{uid}> – Level **{level_from_xp(v['xp'])}** ({v['xp']} XP)"
                 for i, (uid, v) in enumerate(ranking)]
        await ctx.send(embed=embed("🏆 Rangliste", "\n".join(lines)), allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="levelrolle", description="Rolle ab einem bestimmten Level vergeben")
    @commands.has_permissions(administrator=True)
    async def levelrolle(self, ctx, level: commands.Range[int, 1, 500], rolle: discord.Role):
        if rolle >= ctx.guild.me.top_role:
            raise BotError("Diese Rolle liegt über meiner.")
        self.g(ctx.guild)["level_roles"][str(level)] = rolle.id
        self.store.save()
        await ctx.send(f"✅ Ab **Level {level}** gibt es {rolle.mention}.", allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="levelrolle_entfernen", description="Level-Rolle löschen")
    @commands.has_permissions(administrator=True)
    async def levelrolle_entfernen(self, ctx, level: int):
        if self.g(ctx.guild)["level_roles"].pop(str(level), None) is None:
            raise BotError("Für dieses Level gibt es keine Rolle.")
        self.store.save()
        await ctx.send("✅ Entfernt.")

    @commands.hybrid_command(name="levelsystem", description="Level-System an- oder ausschalten")
    @commands.has_permissions(administrator=True)
    async def levelsystem(self, ctx, status: Literal["an", "aus"]):
        self.g(ctx.guild)["levels_on"] = status == "an"
        self.store.save()
        await ctx.send(f"✅ Level-System: **{status}**")

    @commands.hybrid_command(name="xpsetzen", description="XP eines Mitglieds setzen")
    @commands.has_permissions(administrator=True)
    async def xpsetzen(self, ctx, mitglied: discord.Member, xp: commands.Range[int, 0, 10_000_000]):
        self.g(ctx.guild)["levels"][str(mitglied.id)] = {"xp": xp}
        self.store.save()
        await ctx.send(f"✅ {mitglied.display_name} hat jetzt **{xp} XP** (Level {level_from_xp(xp)}).")


# ============================================================================
# ECONOMY
# ============================================================================
JOBS = ["pflückst Beeren im Schlumpfwald", "hilfst Papa Schlumpf im Labor", "backst Kuchen für Schlumpfine",
        "reparierst ein Pilzhaus", "fängst Fische am Schlumpfbach", "spielst auf dem Dorffest Musik"]


class Economy(commands.Cog, name="Economy"):
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store

    def acct(self, guild, uid) -> dict:
        return self.store.guild(guild.id)["eco"].setdefault(str(uid), {"bal": 0, "daily": 0, "work": 0})

    @commands.hybrid_command(name="taeglich", aliases=["daily"], description="Tägliche Belohnung abholen")
    async def taeglich(self, ctx):
        a, now = self.acct(ctx.guild, ctx.author.id), time.time()
        if now - a["daily"] < 86400:
            raise BotError(f"Komm in **{fmt_duration(86400 - (now - a['daily']))}** wieder.")
        gain = random.randint(100, 200)
        a["bal"] += gain
        a["daily"] = now
        self.store.save()
        await ctx.send(embed=embed("🎁 Tägliche Belohnung", f"Du bekommst **{gain}** {CURRENCY}!\nKontostand: **{a['bal']}**", GREEN))

    @commands.hybrid_command(name="arbeiten", aliases=["work"], description="Arbeiten und Beeren verdienen (1x pro Stunde)")
    async def arbeiten(self, ctx):
        a, now = self.acct(ctx.guild, ctx.author.id), time.time()
        if now - a["work"] < 3600:
            raise BotError(f"Du bist noch müde. Warte **{fmt_duration(3600 - (now - a['work']))}**.")
        gain = random.randint(30, 90)
        a["bal"] += gain
        a["work"] = now
        self.store.save()
        await ctx.send(embed=embed("💼 Arbeit", f"Du {random.choice(JOBS)} und verdienst **{gain}** {CURRENCY}.", GREEN))

    @commands.hybrid_command(name="konto", aliases=["balance", "bal"], description="Kontostand anzeigen")
    async def konto(self, ctx, mitglied: discord.Member = None):
        m = mitglied or ctx.author
        await ctx.send(embed=embed(f"💰 Konto von {m.display_name}", f"**{self.acct(ctx.guild, m.id)['bal']}** {CURRENCY}"))

    @commands.hybrid_command(name="zocken", aliases=["gamble"], description="Setze Beeren – 45% Gewinnchance (doppelt)")
    async def zocken(self, ctx, einsatz: commands.Range[int, 1, 10000]):
        a = self.acct(ctx.guild, ctx.author.id)
        if einsatz > a["bal"]:
            raise BotError(f"Du hast nur **{a['bal']}** {CURRENCY}.")
        if random.randint(1, 100) <= 45:
            a["bal"] += einsatz
            e = embed("🎰 Gewonnen!", f"Du gewinnst **{einsatz}** {CURRENCY}!\nKontostand: **{a['bal']}**", GREEN)
        else:
            a["bal"] -= einsatz
            e = embed("🎰 Verloren!", f"Du verlierst **{einsatz}** {CURRENCY}.\nKontostand: **{a['bal']}**", RED)
        self.store.save()
        await ctx.send(embed=e)

    @commands.hybrid_command(name="geben", aliases=["pay"], description="Beeren an ein Mitglied schicken")
    async def geben(self, ctx, mitglied: discord.Member, betrag: commands.Range[int, 1, 1000000]):
        if mitglied.bot or mitglied.id == ctx.author.id:
            raise BotError("Das geht nicht.")
        me, other = self.acct(ctx.guild, ctx.author.id), self.acct(ctx.guild, mitglied.id)
        if betrag > me["bal"]:
            raise BotError(f"Du hast nur **{me['bal']}** {CURRENCY}.")
        me["bal"] -= betrag
        other["bal"] += betrag
        self.store.save()
        await ctx.send(f"💸 {ctx.author.mention} gibt {mitglied.mention} **{betrag}** {CURRENCY}.")

    @commands.hybrid_command(name="reichste", aliases=["richest"], description="Die reichsten Mitglieder")
    async def reichste(self, ctx):
        eco = self.store.guild(ctx.guild.id)["eco"]
        ranking = sorted(((u, v["bal"]) for u, v in eco.items() if v["bal"] > 0), key=lambda x: x[1], reverse=True)[:10]
        if not ranking:
            raise BotError("Noch hat niemand Beeren.")
        lines = [f"**{i}.** <@{u}> – {b} {CURRENCY}" for i, (u, b) in enumerate(ranking, 1)]
        await ctx.send(embed=embed("💎 Die Reichsten", "\n".join(lines)), allowed_mentions=discord.AllowedMentions.none())


# ============================================================================
# FUN
# ============================================================================
WITZE = [
    "Was sagt ein Schlumpf, wenn er keine Lust mehr hat? – Ich bin schlumpf-müde!",
    "Warum können Geister so schlecht lügen? – Man sieht direkt durch sie hindurch.",
    "Was ist grün und klopft an die Tür? – Ein Klopfsalat.",
    "Treffen sich zwei Jäger im Wald. Beide tot.",
    "Was macht ein Pirat am Computer? – Er drückt die Enter-Taste.",
    "Wie nennt man einen Bumerang, der nicht zurückkommt? – Stock.",
    "Warum ging die Tomate nicht ins Rennen? – Sie konnte nicht ketchup.",
    "Was ist braun, klebrig und läuft durch die Wüste? – Ein Karamel.",
    "Warum hat der Skelett-Hund keine Freunde? – Er hat keinen Mumm.",
    "Was sagt der große Stift zum kleinen Stift? – Wachs-mal-stift!",
]
ACHTBALL = ["Ja, definitiv! ✅", "Auf jeden Fall!", "Sieht gut aus.", "Ich glaube schon.", "Frag später nochmal. 🤔",
            "Dazu sage ich nichts.", "Eher nicht.", "Meine Quellen sagen nein. ❌", "Auf keinen Fall!", "Schlumpf-sicher: Ja! 💙"]
WAHRHEIT = ["Was war dein peinlichster Moment?", "Wen auf diesem Server findest du am lustigsten?",
            "Was ist deine größte Angst?", "Welche Serie schaust du heimlich?", "Was war deine schlimmste Lüge?",
            "Welches Talent hättest du gern?", "Was war dein letzter Google-Suchbegriff?", "Was nervt dich an dir selbst?"]
PFLICHT = ["Schreibe 1 Minute lang nur in Großbuchstaben.", "Ändere deinen Nickname für 10 Minuten in „Schlumpf“.",
           "Sing ein Lied im Voice-Chat.", "Mache 10 Kniebeugen und schick ein Beweisfoto-Emoji.",
           "Erzähle einen Witz im Chat.", "Schreibe ein Gedicht über den Server.", "Sprich 2 Minuten wie ein Pirat."]
FAKTEN = ["Honig wird nie schlecht – man hat essbaren Honig in ägyptischen Gräbern gefunden.",
          "Oktopusse haben drei Herzen.", "Bananen sind botanisch gesehen Beeren, Erdbeeren nicht.",
          "Ein Tag auf der Venus ist länger als ein Jahr auf der Venus.", "Wombats produzieren würfelförmigen Kot.",
          "Die Schlümpfe wurden 1958 vom belgischen Zeichner Peyo erfunden.", "Der Eiffelturm wird im Sommer bis zu 15 cm höher."]
ROASTS = ["Du bist so langsam, dass dein Ping ein Brief ist. 📮", "Dein WLAN hat mehr Verbindungsabbrüche als deine Pläne.",
          "Du bist der Grund, warum Shampoo Anleitungen hat.", "Wenn Faulheit eine Sportart wäre, wärst du im Nationalkader. 🏅",
          "Du bist wie ein Update – keiner will dich, aber du kommst trotzdem."]
KOMPLIMENTE = ["Du bist einfach großartig! 🌟", "Dein Lächeln macht den Server heller. ☀️", "Du bist ein echter Schatz. 💎",
               "Mit dir wird jeder Chat besser. 💙", "Du hast ein Herz aus Gold. 🏆"]
WINS = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


class TTTButton(discord.ui.Button):
    def __init__(self, idx: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=idx // 3)
        self.idx = idx

    async def callback(self, inter: discord.Interaction):
        v: "TTTView" = self.view
        if inter.user != v.players[v.turn]:
            return await inter.response.send_message("Du bist nicht dran! ⛔", ephemeral=True)
        self.label = "X" if v.turn == 0 else "O"
        self.style = discord.ButtonStyle.danger if v.turn == 0 else discord.ButtonStyle.success
        self.disabled = True
        v.board[self.idx] = v.turn
        win = any(all(v.board[i] == v.turn for i in line) for line in WINS)
        if win or all(b is not None for b in v.board):
            for c in v.children:
                c.disabled = True
            v.stop()
            text = f"🏆 {inter.user.mention} gewinnt!" if win else "🤝 Unentschieden!"
        else:
            v.turn = 1 - v.turn
            text = f"❌⭕ {v.players[v.turn].mention} ist dran ({'X' if v.turn == 0 else 'O'})"
        await inter.response.edit_message(content=text, view=v)


class TTTView(discord.ui.View):
    def __init__(self, p1, p2):
        super().__init__(timeout=300)
        self.players, self.turn, self.board = [p1, p2], 0, [None] * 9
        for i in range(9):
            self.add_item(TTTButton(i))


class Fun(commands.Cog, name="Fun"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="witz", description="Zufälliger Witz")
    async def witz(self, ctx):
        await ctx.send(embed=embed("😂 Witz", random.choice(WITZE)))

    @commands.hybrid_command(name="8ball", description="Stelle der magischen Kugel eine Frage")
    async def achtball(self, ctx, *, frage: str):
        await ctx.send(embed=embed("🎱 Magische Kugel", f"**Frage:** {frage}\n**Antwort:** {random.choice(ACHTBALL)}"))

    @commands.hybrid_command(name="wuerfel", aliases=["dice"], description="Würfel werfen")
    async def wuerfel(self, ctx, seiten: commands.Range[int, 2, 1000] = 6):
        await ctx.send(f"🎲 Du hast eine **{random.randint(1, seiten)}** gewürfelt (W{seiten}).")

    @commands.hybrid_command(name="muenze", aliases=["coinflip"], description="Münze werfen")
    async def muenze(self, ctx):
        await ctx.send(f"🪙 **{random.choice(['Kopf', 'Zahl'])}**!")

    @commands.hybrid_command(name="schnickschnackschnuck", aliases=["sss"], description="Schere, Stein, Papier gegen den Bot")
    async def sss(self, ctx, wahl: str):
        wahl = wahl.lower().replace("ü", "ue")
        if wahl not in ("schere", "stein", "papier"):
            raise BotError("Wähle `schere`, `stein` oder `papier`.")
        bot_wahl = random.choice(["schere", "stein", "papier"])
        if wahl == bot_wahl:
            res = "Unentschieden! 🤝"
        elif (wahl, bot_wahl) in {("schere", "papier"), ("stein", "schere"), ("papier", "stein")}:
            res = "Du gewinnst! 🎉"
        else:
            res = "Ich gewinne! 😎"
        await ctx.send(f"Du: **{wahl}** | Ich: **{bot_wahl}**\n{res}")

    @commands.hybrid_command(name="ship", description="Wie gut passen zwei Mitglieder zusammen?")
    async def ship(self, ctx, person1: discord.Member, person2: discord.Member):
        key = "".join(sorted([str(person1.id), str(person2.id)]))
        pct = int(hashlib.md5(key.encode()).hexdigest(), 16) % 101
        bar = "💙" * (pct // 10) + "🖤" * (10 - pct // 10)
        await ctx.send(embed=embed("💘 Ship-O-Meter", f"{person1.mention} + {person2.mention}\n\n{bar}\n**{pct}%**"))

    @commands.hybrid_command(name="wahrheit", description="Eine Wahrheitsfrage")
    async def wahrheit(self, ctx):
        await ctx.send(embed=embed("🤔 Wahrheit", random.choice(WAHRHEIT)))

    @commands.hybrid_command(name="pflicht", description="Eine Pflichtaufgabe")
    async def pflicht(self, ctx):
        await ctx.send(embed=embed("😈 Pflicht", random.choice(PFLICHT)))

    @commands.hybrid_command(name="fakt", description="Ein zufälliger Fakt")
    async def fakt(self, ctx):
        await ctx.send(embed=embed("🧠 Wusstest du?", random.choice(FAKTEN)))

    @commands.hybrid_command(name="roast", description="Freundlich-frecher Spruch für ein Mitglied")
    async def roast(self, ctx, mitglied: discord.Member = None):
        await ctx.send(f"{(mitglied or ctx.author).mention} {random.choice(ROASTS)}")

    @commands.hybrid_command(name="kompliment", description="Mache jemandem ein Kompliment")
    async def kompliment(self, ctx, mitglied: discord.Member = None):
        await ctx.send(f"{(mitglied or ctx.author).mention} {random.choice(KOMPLIMENTE)}")

    @commands.hybrid_command(name="umarmen", aliases=["hug"], description="Jemanden umarmen")
    async def umarmen(self, ctx, mitglied: discord.Member):
        await ctx.send(f"🤗 {ctx.author.mention} umarmt {mitglied.mention}!")

    @commands.hybrid_command(name="hauen", aliases=["slap"], description="Jemanden (liebevoll) hauen")
    async def hauen(self, ctx, mitglied: discord.Member):
        await ctx.send(f"👊 {ctx.author.mention} haut {mitglied.mention} mit einem nassen Fisch. 🐟")

    @commands.hybrid_command(name="bewerte", aliases=["rate"], description="Bewerte irgendetwas von 0 bis 10")
    async def bewerte(self, ctx, *, was: str):
        score = int(hashlib.md5(was.lower().encode()).hexdigest(), 16) % 11
        await ctx.send(embed=embed("⭐ Bewertung", f"**{was}**\n{'⭐' * score}{'▫️' * (10 - score)} **{score}/10**"),
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="waehle", aliases=["choose"], description="Entscheidet zwischen Optionen (mit | trennen)")
    async def waehle(self, ctx, *, optionen: str):
        opts = [o.strip() for o in (optionen.split("|") if "|" in optionen else optionen.split(","))if o.strip()]
        if len(opts) < 2:
            raise BotError("Gib mindestens zwei Optionen an: `!waehle Pizza | Pasta | Döner`")
        await ctx.send(f"🤔 Ich wähle: **{random.choice(opts)}**", allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="umdrehen", aliases=["reverse"], description="Text rückwärts schreiben")
    async def umdrehen(self, ctx, *, text: str):
        await ctx.send(text[::-1], allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="schlumpf", description="Verschlumpfe einen Text")
    async def schlumpf(self, ctx, *, text: str):
        out = [("schlumpf" if len(w) > 3 and random.random() < 0.4 else w) for w in text.split()]
        await ctx.send("💙 " + " ".join(out), allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="tictactoe", aliases=["ttt"], description="Tic-Tac-Toe gegen ein Mitglied spielen")
    async def tictactoe(self, ctx, gegner: discord.Member):
        if gegner.bot or gegner.id == ctx.author.id:
            raise BotError("Such dir einen echten Gegner. 😄")
        await ctx.send(f"❌⭕ {ctx.author.mention} (X) fordert {gegner.mention} (O) heraus!\n{ctx.author.mention} beginnt.",
                       view=TTTView(ctx.author, gegner))


# ============================================================================
# UTILITY
# ============================================================================
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
            "`!umfrage` `!giveaway` `!erinnere` `!afk` `!sag` `!embed` `!ping` `!rechte` `!botinfo` `!serverinfo` `!userinfo` `!avatar`"))
        e.add_field(name="⚙️ Setup (Admin)", inline=False, value=(
            "`!setwillkommen` `!setgoodbye` `!setlog` `!setautorolle` `!willkommentext` `!willkommentest`\n"
            "`!reaktionsrolle` `!call setup` `!einstellungen`"))
        await ctx.send(embed=e)

    @commands.hybrid_command(name="ping", description="Latenz des Bots")
    async def ping(self, ctx):
        await ctx.send(f"🏓 Pong! `{round(self.bot.latency * 1000)} ms`")

    @commands.hybrid_command(name="rechte", description="Prüft, welche Rechte der Bot auf dem Server hat")
    async def rechte(self, ctx):
        me = ctx.guild.me
        p = me.guild_permissions
        names = [("administrator", "Administrator"), ("manage_channels", "Kanäle verwalten"),
                 ("move_members", "Mitglieder verschieben"), ("kick_members", "Mitglieder kicken"),
                 ("ban_members", "Mitglieder bannen"), ("moderate_members", "Mitglieder moderieren (Timeout)"),
                 ("manage_messages", "Nachrichten verwalten"), ("manage_roles", "Rollen verwalten"),
                 ("manage_nicknames", "Nicknames verwalten"), ("manage_guild", "Server verwalten")]
        lines = [f"{'✅' if getattr(p, k) else '❌'} {v}" for k, v in names]
        top = me.top_role
        lines.append(f"\n**Höchste Bot-Rolle:** {top.mention} (Position {top.position} von {len(ctx.guild.roles) - 1})")
        hint = ("✅ Der Bot hat Administrator – alles in Ordnung." if p.administrator else
                "⚠️ Der Bot hat **kein** Administrator. Aktiviere es unter Servereinstellungen → Rollen → "
                f"**{top.name}** → Berechtigungen → Administrator.")
        await ctx.send(embed=embed("🔐 Bot-Rechte", "\n".join(lines) + "\n\n" + hint))

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


# ============================================================================
# ZEIT
# ============================================================================
class Zeit(commands.Cog, name="Zeit"):
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store

    async def cog_load(self):
        self.checker.start()

    async def cog_unload(self):
        self.checker.cancel()

    @tasks.loop(seconds=10)
    async def checker(self):
        now = time.time()
        # Giveaways
        for gid, g in list(self.store.data["guilds"].items()):
            for mid, gw in list(g.get("giveaways", {}).items()):
                if gw["end"] <= now:
                    g["giveaways"].pop(mid, None)
                    self.store.save()
                    try:
                        await self.finish_giveaway(int(mid), gw)
                    except Exception as e:
                        log.error("Giveaway-Fehler: %s", e)
        # Erinnerungen
        rem = self.store.data["reminders"]
        due = [r for r in rem if r["end"] <= now]
        if due:
            self.store.data["reminders"] = [r for r in rem if r["end"] > now]
            self.store.save()
        for r in due:
            ch = self.bot.get_channel(r["channel"])
            text = f"⏰ <@{r['user']}> Erinnerung: **{r['text']}**"
            try:
                if ch:
                    await ch.send(text)
                else:
                    user = await self.bot.fetch_user(r["user"])
                    await user.send(text)
            except discord.HTTPException:
                pass

    @checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------ Giveaways
    async def pick_winners(self, message: discord.Message, n: int):
        reaction = discord.utils.get(message.reactions, emoji="🎉")
        if not reaction:
            return []
        users = [u async for u in reaction.users() if not u.bot]
        return random.sample(users, min(n, len(users)))

    async def finish_giveaway(self, mid: int, gw: dict):
        ch = self.bot.get_channel(gw["channel"])
        if not ch:
            return
        msg = await ch.fetch_message(mid)
        winners = await self.pick_winners(msg, gw["winners"])
        if winners:
            names = ", ".join(w.mention for w in winners)
            result = f"🎉 Glückwunsch {names}! Du hast **{gw['prize']}** gewonnen!"
        else:
            result = f"😢 Bei **{gw['prize']}** hat niemand teilgenommen."
        await msg.edit(embed=embed("🎉 Giveaway beendet", f"**{gw['prize']}**\n\nGewinner: "
                                   + (", ".join(w.mention for w in winners) or "—")))
        await ch.send(result)

    @commands.hybrid_group(name="giveaway", fallback="hilfe", invoke_without_command=True,
                           description="Giveaways: Hilfe")
    async def giveaway(self, ctx):
        await ctx.send(embed=embed("🎉 Giveaways",
                                   "`!giveaway start <dauer> <gewinner> <preis>` – z.B. `!giveaway start 1h 1 Nitro`\n"
                                   "`!giveaway ende <nachricht_id>` – sofort beenden\n"
                                   "`!giveaway neuziehen <nachricht_id>` – neu auslosen (im selben Kanal)"))

    @giveaway.command(name="start", description="Giveaway starten (Dauer z.B. 30m, 2h, 1d)")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_start(self, ctx, dauer: str, gewinner: commands.Range[int, 1, 20], *, preis: str):
        secs = parse_duration(dauer)
        if not secs or secs > 30 * 86400:
            raise BotError("Ungültige Dauer. Beispiele: `30m`, `2h`, `1d` (maximal 30 Tage).")
        end = time.time() + secs
        e = embed("🎉 GIVEAWAY 🎉",
                  f"**{preis}**\n\nReagiere mit 🎉 zum Mitmachen!\nEndet {discord.utils.format_dt(discord.utils.utcnow() + timedelta(seconds=secs), 'R')}\n"
                  f"Gewinner: **{gewinner}** · Gestartet von {ctx.author.mention}")
        msg = await ctx.channel.send(embed=e)
        await msg.add_reaction("🎉")
        self.store.guild(ctx.guild.id)["giveaways"][str(msg.id)] = {
            "channel": ctx.channel.id, "end": end, "winners": gewinner, "prize": preis}
        self.store.save()
        await ctx.send(f"✅ Giveaway gestartet ({fmt_duration(secs)}).", ephemeral=True)

    @giveaway.command(name="ende", description="Giveaway sofort beenden")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_ende(self, ctx, nachricht_id: str):
        gw = self.store.guild(ctx.guild.id)["giveaways"].get(nachricht_id)
        if not gw:
            raise BotError("Dieses Giveaway läuft nicht (mehr).")
        gw["end"] = 0
        self.store.save()
        await ctx.send("✅ Wird in wenigen Sekunden beendet.", ephemeral=True)

    @giveaway.command(name="neuziehen", description="Neuen Gewinner auslosen (im Kanal des Giveaways)")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_neuziehen(self, ctx, nachricht_id: str):
        try:
            msg = await ctx.channel.fetch_message(int(nachricht_id))
        except (ValueError, discord.NotFound):
            raise BotError("Nachricht in diesem Kanal nicht gefunden.")
        winners = await self.pick_winners(msg, 1)
        if not winners:
            raise BotError("Keine Teilnehmer gefunden.")
        await ctx.send(f"🎉 Neuer Gewinner: {winners[0].mention}! Glückwunsch!")

    # ----------------------------------------------------------- Erinnerungen
    @commands.hybrid_command(name="erinnere", aliases=["remind", "erinnerung"],
                             description="Erinnerung setzen: !erinnere 10m Pizza holen")
    async def erinnere(self, ctx, dauer: str, *, text: str):
        secs = parse_duration(dauer)
        if not secs or secs > 30 * 86400:
            raise BotError("Ungültige Dauer. Beispiele: `10m`, `2h`, `1d` (maximal 30 Tage).")
        self.store.data["reminders"].append({"user": ctx.author.id, "channel": ctx.channel.id,
                                             "end": time.time() + secs, "text": text[:300]})
        self.store.save()
        await ctx.send(f"⏰ Ich erinnere dich in **{fmt_duration(secs)}** an: {text[:300]}",
                       allowed_mentions=discord.AllowedMentions.none())


COGS = [Server, Moderation, Calls, Tickets, Levels, Economy, Fun, Utility, Zeit]


# ============================================================================
# BOT
# ============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "!"


intents = discord.Intents.default()
intents.members = True          # im Developer Portal aktivieren!
intents.message_content = True  # im Developer Portal aktivieren!


async def guild_only(ctx: commands.Context) -> bool:
    if ctx.guild is None:
        raise commands.NoPrivateMessage()
    return True


class SchlumpfBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX),
            intents=intents,
            help_command=None,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
        )
        self.store = Store()
        self.start_time = discord.utils.utcnow()

    async def setup_hook(self):
        self.add_check(guild_only)
        for cog in COGS:
            await self.add_cog(cog(self))
            log.info("Modul geladen: %s", cog.__name__)
        self.autosave.start()
        synced = await self.tree.sync()
        log.info("%d Slash-Commands synchronisiert.", len(synced))
        try:  # Railway sendet SIGTERM beim Neustart -> Daten vorher sichern
            asyncio.get_running_loop().add_signal_handler(
                signal.SIGTERM, lambda: asyncio.create_task(self.close()))
        except (NotImplementedError, RuntimeError):
            pass

    @tasks.loop(seconds=30)
    async def autosave(self):
        self.store.flush()

    async def close(self):
        self.store.save()
        await super().close()

    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, name=f"{SERVER_NAME} | !hilfe"))
        log.info("Eingeloggt als %s (%s) – %d Server", self.user, self.user.id, len(self.guilds))

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        for _ in range(3):  # verpackte Fehler auspacken
            if isinstance(error, (commands.CommandInvokeError, commands.HybridCommandError,
                                  app_commands.CommandInvokeError)):
                error = error.original

        if isinstance(error, commands.CommandNotFound):
            return
        usage = f"`{PREFIX}{ctx.command.qualified_name} {ctx.command.signature}`" if ctx.command else ""

        if isinstance(error, BotError):
            msg = f"❌ {error}"
        elif isinstance(error, commands.MissingPermissions):
            msg = "❌ Dafür hast du keine Berechtigung."
        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(error.missing_permissions)
            msg = f"❌ Mir fehlen Rechte auf dem Server: `{perms}`"
        elif isinstance(error, commands.NoPrivateMessage):
            msg = "❌ Das geht nur auf einem Server."
        elif isinstance(error, commands.CommandOnCooldown):
            msg = f"⏳ Bitte warte noch {error.retry_after:.0f} Sekunden."
        elif isinstance(error, commands.UserInputError):
            msg = f"❌ Ungültige Eingabe.\nNutzung: {usage}"
        elif isinstance(error, commands.CheckFailure):
            msg = "❌ Das darfst du hier nicht."
        elif isinstance(error, discord.Forbidden):
            msg = "❌ Mir fehlt die Berechtigung dafür (Rollenreihenfolge/Rechte prüfen)."
        else:
            log.error("Fehler in Befehl %s", ctx.command, exc_info=error)
            msg = "❌ Da ist etwas schiefgelaufen."
        try:
            await ctx.send(msg, ephemeral=True)
        except discord.HTTPException:
            pass


bot = SchlumpfBot()

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Fehler: Umgebungsvariable DISCORD_TOKEN ist nicht gesetzt!")
    bot.run(TOKEN, log_handler=None)
