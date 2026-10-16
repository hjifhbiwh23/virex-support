"""
SCHLUMPF SKANDI – Discord Bot (Deutsch)
Alle Befehle funktionieren mit  !befehl  UND  /befehl  (Hybrid-Commands).
Start:  python bot.py   (Token in der Umgebungsvariable DISCORD_TOKEN)
"""
import asyncio
import logging
import os
import signal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import SERVER_NAME, BotError, Store, log

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "!"

EXTENSIONS = [
    "cogs.server", "cogs.moderation", "cogs.calls", "cogs.tickets", "cogs.levels",
    "cogs.economy", "cogs.fun", "cogs.utility", "cogs.zeit",
]

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
        for ext in EXTENSIONS:
            await self.load_extension(ext)
            log.info("Modul geladen: %s", ext)
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
