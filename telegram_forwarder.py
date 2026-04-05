"""
Telegram Channel Forwarder
Monitors public news channels and forwards posts to your own channel.
Uses a Telegram user account (Telethon) — not a bot — so it can read any public channel.

Setup:
  1. Get API credentials at https://my.telegram.org/apps
  2. Set TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_TARGET_CHANNEL in .env
  3. pip install telethon
  4. python telegram_forwarder.py
     (first run: you'll be asked to log in with your phone number)
"""

import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient, events

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TARGET_CHANNEL = os.getenv("TELEGRAM_TARGET_CHANNEL", "@polynews_crypto")

# Channels to monitor — add/remove as needed
SOURCE_CHANNELS = [
    # Crypto / Finance
    "@bitcoin",
    "@WuBlockchain",
    "@unusual_whales",
    "@coinbureau",
    # News / Politics
    "@reuters",
    "@bbcnews",
    "@thehill",
    "@politico",
    # Tech / AI
    "@techcrunchofficial",
]

if not API_ID or not API_HASH:
    raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env — get them at https://my.telegram.org/apps")

if not TARGET_CHANNEL:
    raise SystemExit("Set TELEGRAM_TARGET_CHANNEL in .env (e.g. @your_channel_username)")

client = TelegramClient("forwarder_session", API_ID, API_HASH)


@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def forward(event):
    if event.message and event.message.text:
        source = event.chat.username or str(event.chat_id)
        print(f"[{source}] {event.message.text[:80]}...")
        await client.forward_messages(TARGET_CHANNEL, event.message)


async def main():
    await client.start()
    print(f"Forwarder running — watching {len(SOURCE_CHANNELS)} channels → {TARGET_CHANNEL}")
    print("Press Ctrl+C to stop.\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
