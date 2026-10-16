# SCHLUMPF SKANDI – Discord Bot

Alle Befehle funktionieren mit `!befehl` **und** `/befehl`. Hilfe im Server: `!hilfe`

## Railway
1. Ordner auf GitHub hochladen → Railway: *New Project → Deploy from GitHub*
2. Variable `DISCORD_TOKEN` setzen
3. Optional (damit Daten Neustarts überleben): Volume nach `/data` mounten und `DATA_DIR=/data` setzen

## Developer Portal
Bot → *Privileged Gateway Intents*: **Server Members** und **Message Content** aktivieren.
Bot mit Administrator-Recht einladen (Scopes: `bot`, `applications.commands`)
und seine Rolle ganz nach oben schieben.

## Erste Einrichtung (im Server)
```
!call setup                 -> erstellt "➕ Call erstellen" (Join-to-Create)
!setwillkommen #willkommen
!setgoodbye #verlassen
!setlog #mod-log
!ticket setup               -> im Support-Kanal; optional: !ticket setup #kategorie @supportrolle
!setautorolle @Mitglied
```
