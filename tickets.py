"""Ticket-System mit Buttons und Transkript."""
import asyncio
import io
import re

import discord
from discord.ext import commands

from utils import BotError, embed, find_channel


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


async def setup(bot):
    await bot.add_cog(Tickets(bot))
