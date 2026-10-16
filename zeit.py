"""Zeitgesteuert: Giveaways und Erinnerungen (überleben Neustarts)."""
import random
import time
from datetime import timedelta

import discord
from discord.ext import commands, tasks

from utils import BotError, embed, fmt_duration, log, parse_duration


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


async def setup(bot):
    await bot.add_cog(Zeit(bot))
