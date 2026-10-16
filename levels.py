"""Level-System: XP durch Schreiben, Rang, Rangliste, Level-Rollen."""
import random
import time
from typing import Literal

import discord
from discord.ext import commands

from utils import BotError, embed


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


async def setup(bot):
    await bot.add_cog(Levels(bot))
