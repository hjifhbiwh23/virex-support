# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY discord_bot_with_blacklist.py bot.py

# Run bot
CMD ["python", "discord_bot_with_blacklist.py"]
