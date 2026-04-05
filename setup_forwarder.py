"""
Interactive setup for Telegram forwarder credentials.
Credentials are stored in .env2 — never printed to terminal.

Usage:
    python setup_forwarder.py
"""

import getpass
import os
import re
import sys
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env2"


def read_env() -> dict:
    if not ENV_FILE.exists():
        return {}
    result = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def write_env(updates: dict):
    """Update or append key=value pairs in .env2 without touching other lines."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    updated_keys = set()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            lines[i] = f"{key}={updates[key]}"
            updated_keys.add(key)

    for key, value in updates.items():
        if key not in updated_keys:
            lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(lines) + "\n")


def prompt_secure(label: str, current: str = "") -> str:
    """Prompt for sensitive input — not echoed to terminal."""
    hint = " [keep existing]" if current else ""
    value = getpass.getpass(f"  {label}{hint}: ")
    if not value and current:
        return current
    return value.strip()


def prompt_plain(label: str, current: str = "") -> str:
    hint = f" [{current}]" if current else ""
    value = input(f"  {label}{hint}: ").strip()
    return value if value else current


def validate_api_id(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value))


def main():
    print("\n=== Telegram Forwarder Setup ===\n")
    print("Credentials are stored in .env2 and never shown in the terminal.\n")

    env = read_env()

    # --- API credentials ---
    print("Step 1: Telegram API credentials (from https://my.telegram.org/apps)\n")

    api_id = ""
    while not validate_api_id(api_id):
        api_id = prompt_secure("TELEGRAM_API_ID (numbers only)", env.get("TELEGRAM_API_ID", ""))
        if not validate_api_id(api_id):
            print("  ! Must be numeric. Try again.")

    api_hash = ""
    while len(api_hash) < 10:
        api_hash = prompt_secure("TELEGRAM_API_HASH", env.get("TELEGRAM_API_HASH", ""))
        if len(api_hash) < 10:
            print("  ! Too short. Try again.")

    # --- Target channel ---
    print("\nStep 2: Your destination channel\n")
    target = ""
    while not target:
        target = prompt_plain("TELEGRAM_TARGET_CHANNEL (e.g. @polynews_crypto)", env.get("TELEGRAM_TARGET_CHANNEL", "@polynews_crypto"))
        if not target:
            print("  ! Required.")

    if not target.startswith("@") and not target.lstrip("-").isdigit():
        target = f"@{target}"

    # --- Save ---
    write_env({
        "TELEGRAM_API_ID": api_id,
        "TELEGRAM_API_HASH": api_hash,
        "TELEGRAM_TARGET_CHANNEL": target,
    })

    print(f"\n✓ Credentials saved to {ENV_FILE}")
    print(f"  Target channel : {target}")
    print(f"  API ID         : {'*' * len(api_id)}")
    print(f"  API Hash       : {'*' * len(api_hash)}")

    # --- Test Telethon import ---
    print("\nStep 3: Checking dependencies...\n")
    try:
        import telethon  # noqa
        print("  ✓ telethon is installed")
    except ImportError:
        print("  ! telethon not found. Installing...")
        os.system(f"{sys.executable} -m pip install telethon")

    print("\nSetup complete. Run the forwarder with:\n")
    print("    python telegram_forwarder.py\n")
    print("First run will ask for your phone number + Telegram OTP to log in.\n")


if __name__ == "__main__":
    main()
