"""
verify-live — pre-flight check for live trading.

Confirms your credentials are correct and your account can trade, WITHOUT
placing any order. Catches the common mistakes:
  - using the API-key UUID instead of the 64-hex wallet private key
  - a missing/wrong funder address
  - the wrong signature type for a proxy wallet
  - no USDC balance or allowances

Run: python cli.py verify-live
"""
from __future__ import annotations

import re

from rich.console import Console
from rich.panel import Panel

import config

console = Console()

# A wallet private key is 64 hex chars, optionally 0x-prefixed.
_PRIVKEY_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")
# UUID shape — the API-key ID users often paste by mistake.
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _pass(msg): console.print(f"  [bright_green]PASS[/bright_green]  {msg}")
def _fail(msg): console.print(f"  [red]FAIL[/red]  {msg}")
def _warn(msg): console.print(f"  [yellow]WARN[/yellow]  {msg}")


def run_verify_live() -> bool:
    console.print(Panel("[bold]LIVE TRADING PRE-FLIGHT[/bold] — no orders are placed", style="bright_cyan"))
    ok = True

    # 1. Private key format — the mistake that bites everyone.
    key = config.POLYMARKET_PRIVATE_KEY.strip()
    if not key:
        _fail("POLYMARKET_PRIVATE_KEY not set")
        ok = False
    elif _UUID_RE.match(key):
        _fail("POLYMARKET_PRIVATE_KEY looks like an API-key UUID, not a wallet key.\n"
              "        You need the 64-hex signing key (0x + 64 chars), exported from\n"
              "        your wallet — NOT the Polymarket API key ID.")
        ok = False
    elif not _PRIVKEY_RE.match(key):
        _fail(f"POLYMARKET_PRIVATE_KEY is not a valid 64-hex private key (got {len(key)} chars)")
        ok = False
    else:
        _pass("Private key format looks valid (64-hex)")

    # 2. Funder address format.
    funder = config.POLYMARKET_FUNDER_ADDRESS.strip()
    if not funder:
        _warn("POLYMARKET_FUNDER_ADDRESS not set — required for proxy wallets (sig type 1/2)")
    elif not _ADDR_RE.match(funder):
        _fail(f"POLYMARKET_FUNDER_ADDRESS is not a valid 0x address: {funder[:12]}...")
        ok = False
    else:
        _pass(f"Funder address format valid ({funder[:6]}...{funder[-4:]})")

    # 3. Signature type sanity.
    st = config.POLYMARKET_SIGNATURE_TYPE
    if st not in (0, 1, 2):
        _fail(f"POLYMARKET_SIGNATURE_TYPE must be 0, 1, or 2 (got {st})")
        ok = False
    else:
        names = {0: "EOA (no proxy)", 1: "POLY_PROXY (email/magic)", 2: "POLY_GNOSIS_SAFE (browser wallet)"}
        _pass(f"Signature type {st} — {names[st]}")
        if st == 0 and funder:
            _warn("Sig type 0 (EOA) usually needs NO funder; web-app deposits use 1 or 2")
        if st in (1, 2) and not funder:
            _fail("Sig type 1/2 (proxy) requires POLYMARKET_FUNDER_ADDRESS")
            ok = False

    # 4. DRY_RUN flag.
    if config.DRY_RUN:
        _warn("DRY_RUN=true — the bot will paper-trade. Set DRY_RUN=false to trade live.")
    else:
        _pass("DRY_RUN=false — live orders are ARMED")

    # Stop here if the basics are wrong — don't bother the network.
    if not ok:
        console.print()
        console.print(Panel("[yellow bold]Fix the errors above before going live.[/yellow bold]", style="yellow"))
        return False

    # 5. py-clob-client installed?
    try:
        import py_clob_client  # noqa: F401
        _pass("py-clob-client installed")
    except ImportError:
        _fail("py-clob-client not installed — run: pip install py-clob-client")
        console.print()
        console.print(Panel("[yellow bold]Install the client, then re-run.[/yellow bold]", style="yellow"))
        return False

    # 6. Authenticate (derives API creds from the private key). No order placed.
    try:
        from executor import build_clob_client
        client = build_clob_client()
        _pass("Authenticated with CLOB — API credentials derived from key")
    except Exception as e:
        _fail(f"Auth failed — {type(e).__name__}: {e}")
        console.print()
        console.print(Panel("[yellow bold]Credentials rejected. Check key + funder + sig type.[/yellow bold]", style="yellow"))
        return False

    # 7. USDC balance + allowance (read-only).
    try:
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        bal = client.get_balance_allowance(
            BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
                signature_type=config.POLYMARKET_SIGNATURE_TYPE,
            )
        )
        raw = float(bal.get("balance", 0)) if isinstance(bal, dict) else 0.0
        usdc = raw / 1_000_000  # USDC has 6 decimals
        if usdc > 0:
            _pass(f"USDC balance visible: ${usdc:,.2f}")
        else:
            _warn("USDC balance reads as $0 — deposit funds before live trading")

        # Allowance: the CLOB exchange must be approved to move your USDC.
        allow_raw = bal.get("allowance", bal.get("allowances")) if isinstance(bal, dict) else None
        try:
            allow_val = float(allow_raw) if not isinstance(allow_raw, dict) else max(float(v) for v in allow_raw.values())
        except (TypeError, ValueError):
            allow_val = None
        if allow_val is not None:
            if allow_val > 0:
                _pass("USDC allowance set — CLOB is approved to trade your funds")
            else:
                _warn("USDC allowance is 0 — enable trading in the Polymarket UI once,\n"
                      "        or the client will reject orders. (client.update_balance_allowance)")
    except Exception as e:
        _warn(f"Could not read balance/allowance — {type(e).__name__}: {e}")

    console.print()
    console.print(Panel(
        "[bright_green bold]PRE-FLIGHT PASSED[/bright_green bold]\n\n"
        "Credentials authenticate and the account is reachable. Start small:\n"
        "  MAX_BET_USD=1  python cli.py bot --live",
        style="bright_green",
    ))
    return True
