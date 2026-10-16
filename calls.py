"""Calls: Join-to-Create Sprachkanäle.
Wer den Hub-Kanal betritt (➕ Call erstellen), bekommt einen eigenen Call, der automatisch
gelöscht wird, sobald er leer ist. Der Besitzer kann ihn mit !call ... verwalten."""
import asyncio
import random

import discord
from discord.ext import commands

from utils import BotError, embed, log

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
    @commands.bot_has_permissions(manage_channels=True, move_members=True)
    async def call(self, ctx, *, name: str = None):
        ch, created = await self.create_call(ctx.author, name)
        if ctx.author.voice and ctx.author.voice.channel:
            if ctx.author.voice.channel != ch:
                await ctx.author.move_to(ch)
            return await ctx.send(f"✅ Dein Call: {ch.mention}")
        if created:
            asyncio.create_task(self.cleanup_later(ch))
        await ctx.send(f"✅ Dein Call: {ch.mention} – komm rein! (Wird gelöscht, wenn niemand in 60 Sek. beitritt.)")

    @call.command(name="setup", description="Call-System einrichten (erstellt Kategorie + Hub)")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True, move_members=True)
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


async def setup(bot):
    await bot.add_cog(Calls(bot))
