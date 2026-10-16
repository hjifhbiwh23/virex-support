"""Gemeinsame Hilfsfunktionen und Datenspeicher für den SCHLUMPF SKANDI Bot."""
import copy
import json
import logging
import os
import re
from pathlib import Path

import discord
from discord.ext import commands

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
