#!/bin/bash
# Usage: bash get_credentials.sh <private_key>
# Writes Polymarket CLOB credentials into .env2

if [ -z "$1" ]; then
  echo "Usage: bash get_credentials.sh <private_key>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env2"

python3 - "$1" "$ENV_FILE" <<'EOF'
import sys
try:
    from py_clob_client.client import ClobClient
except ImportError:
    print("Error: py-clob-client not installed. Run: pip install py-clob-client")
    sys.exit(1)

private_key = sys.argv[1]
env_file = sys.argv[2]

try:
    client = ClobClient(host="https://clob.polymarket.com", key=private_key, chain_id=137)
    creds = client.create_or_derive_api_creds()
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

updates = {
    "POLYMARKET_PRIVATE_KEY": private_key,
    "POLYMARKET_API_KEY": creds.api_key,
    "POLYMARKET_API_SECRET": creds.api_secret,
    "POLYMARKET_API_PASSPHRASE": creds.api_passphrase,
}

try:
    with open(env_file, "r") as f:
        lines = f.readlines()
except FileNotFoundError:
    lines = []

result = []
updated = set()
for line in lines:
    key = line.split("=")[0].strip()
    if key in updates:
        result.append(f"{key}={updates[key]}\n")
        updated.add(key)
    else:
        result.append(line)

for key, value in updates.items():
    if key not in updated:
        result.append(f"{key}={value}\n")

with open(env_file, "w") as f:
    f.writelines(result)

print("Credentials written to .env2")
EOF
