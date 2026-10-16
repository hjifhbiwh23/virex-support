"""Unterhaltung & Spiele."""
import hashlib
import random

import discord
from discord.ext import commands

from utils import BotError, embed

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


async def setup(bot):
    await bot.add_cog(Fun(bot))
