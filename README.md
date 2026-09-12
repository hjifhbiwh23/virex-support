# 🏆 Expand By Legacy™ • Esports Discord Bot

A complete, high-performance Discord Bot for Fortnite esports servers. Fully customizable and ready to deploy 24/7 on **Railway**.

---

## ⚡ Features

1. **🎨 Welcomer System**:
   - Dynamic **Image Card Generator** (rounded user avatar, dark esports gradient, outer white border, ordinal member count).
   - Welcome channel message: `Welcome @user! to Expand By Legacy™! You are the Xth member!`.
   - Automatic DM welcome message sent to new members.

2. **🎫 Interactive Ticket System & Transcripts**:
   - Interactive Dropdown menu with 3 categories:
     - ⚔️ **Apply for Member** (Fortnite Roster Application)
     - 🛡️ **Apply for Staff** (Team Management / Moderator Application)
     - ❓ **General Questions & Support**
   - Private ticket channels created automatically with restricted staff access.
   - **Full Transcript Exporter**: Generates a `.txt` transcript file upon closing a ticket and posts it to your transcript log channel.

3. **📢 Anonymous / Bot Echo (`*` Prefix)**:
   - Type any message starting with `*` (e.g. `*Hello Everyone!`).
   - The bot deletes your original message and posts the text as the bot!

4. **🛡️ Moderation Tools (Slash Commands)**:
   - `/kick [user] [reason]` - Kick a member.
   - `/ban [user] [reason]` - Ban a member.
   - `/unban [user_id]` - Unban a user by ID.
   - `/timeout [user] [minutes] [reason]` - Mute a user.
   - `/untimeout [user]` - Remove mute.
   - `/clear [amount]` - Purge up to 100 messages.
   - `/warn [user] [reason]` & `/warnings [user]` - SQLite warning database system.

5. **📜 Server Rules & Tickets Setup**:
   - `/rules` - Send formatted server rules and guidelines embed.
   - `/setup-tickets` - Deploy the interactive ticket panel embed in any channel.

---

## 🚀 How to Deploy on Railway

1. **Create a GitHub Repository**:
   - Push all project files (`bot.py`, `requirements.txt`, `Procfile`, `railway.json`, `.env.example`, `README.md`) to your GitHub repository.

2. **Deploy on Railway**:
   - Go to [Railway.app](https://railway.app) and sign in.
   - Click **New Project** -> **Deploy from GitHub repo**.
   - Select your bot repository.

3. **Add Environment Variables on Railway**:
   - Go to your Railway service **Variables** tab and set:
     - `DISCORD_TOKEN` = *(Your bot token from Discord Developer Portal)*
     - `WELCOME_CHANNEL_ID` = *(Channel ID where welcome cards will be sent)*
     - `LOG_CHANNEL_ID` = *(Channel ID where ticket transcripts will be posted)*
     - `TICKET_CATEGORY_ID` = *(Category ID under which tickets will open)*
     - `STAFF_ROLE_ID` = *(Role ID for staff who can see tickets)*
     - `EMBED_COLOR` = `00A2FF` *(or your custom branding hex color)*

4. **Required Discord Privileged Intents**:
   - Go to [Discord Developer Portal](https://discord.com/developers/applications).
   - Select your bot application -> **Bot** tab.
   - Enable **Server Members Intent** and **Message Content Intent**.

---

## 💻 Local Testing

1. Install Python 3.10+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your variables.
4. Run the bot:
   ```bash
   python bot.py
   ```
