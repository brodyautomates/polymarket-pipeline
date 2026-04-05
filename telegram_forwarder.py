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
TARGET_CHANNEL = os.getenv("TELEGRAM_TARGET_CHANNEL", "@@trading_news_yrii")

# Channels to monitor — add/remove as needed
SOURCE_CHANNELS = [
    "@TreeNewsFeed",
    "@SharkTradeandCrypto",
    "@coin_listing",
    "@wu_blockchain",
    "@CryptoRankNews",
    "@DeFimillion",
    "@whale_alert",
    "@cryptolistingPro",
    "@PeckShieldAlert",
    "@binance_announcements",
    "@cryptodiffer",
    "@CoinMarketCap",
    "@glassnode",
    "@zachxbt",
    "@spotonchain",
    "@icospeaksnews",
    "@icodrops",
    "@polynews_crypto",
]

if not API_ID or not API_HASH:
    raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env — get them at https://my.telegram.org/apps")

if not TARGET_CHANNEL:
    raise SystemExit("Set TELEGRAM_TARGET_CHANNEL in .env (e.g. @your_channel_username)")

client = TelegramClient("forwarder_session", API_ID, API_HASH)


async def resolve_channels():
    """Resolve channel usernames, skipping any that no longer exist."""
    valid = []
    for ch in SOURCE_CHANNELS:
        try:
            await client.get_input_entity(ch)
            valid.append(ch)
        except (ValueError, Exception) as e:
            print(f"⚠ Skipping {ch}: {e}")
    return valid


async def main():
    await client.start()
    valid_channels = await resolve_channels()
    if not valid_channels:
        raise SystemExit("No valid source channels found.")

    @client.on(events.NewMessage(chats=valid_channels))
    async def forward(event):
        if event.message and event.message.text:
            source = event.chat.username or str(event.chat_id)
            print(f"[{source}] {event.message.text[:80]}...")
            await client.forward_messages(TARGET_CHANNEL, event.message)

    print(f"Forwarder running — watching {len(valid_channels)}/{len(SOURCE_CHANNELS)} channels → {TARGET_CHANNEL}")
    print("Press Ctrl+C to stop.\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
