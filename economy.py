"""Mini-Wirtschaft mit Schlumpfbeeren."""
import random
import time

import discord
from discord.ext import commands

from utils import CURRENCY, GREEN, RED, BotError, embed, fmt_duration

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


async def setup(bot):
    await bot.add_cog(Economy(bot))
