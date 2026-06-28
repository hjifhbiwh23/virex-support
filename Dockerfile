FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Alle Dateien kopieren (inkl. index.html)
COPY . .

CMD ["python", "discord_bot_with_blacklist.py"]
