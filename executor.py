from __future__ import annotations

import asyncio

import config
import logger
from edge import Signal
from markets import get_token_id


def execute_trade(signal: Signal) -> dict:
    """Execute a trade on Polymarket or log a dry-run. Synchronous."""
    daily_spent = abs(logger.get_daily_pnl())
    if daily_spent + signal.bet_amount > config.DAILY_LOSS_LIMIT_USD:
        return _log_and_return(signal, status="rejected_daily_limit", order_id=None)

    if config.DRY_RUN:
        return _log_and_return(signal, status="dry_run", order_id=None)

    return _execute_live(signal)


async def execute_trade_async(signal: Signal) -> dict:
    """Async wrapper around execute_trade."""
    return await asyncio.get_event_loop().run_in_executor(None, execute_trade, signal)


def _round_to_tick(price: float, tick: float) -> float:
    """Round a price to the market's tick size, kept strictly inside (0, 1)."""
    if tick <= 0:
        tick = 0.01
    decimals = max(0, len(str(tick).split(".")[-1])) if "." in str(tick) else 0
    rounded = round(round(price / tick) * tick, decimals)
    return min(max(rounded, tick), 1 - tick)


def build_clob_client():
    """
    Construct an authenticated Polymarket CLOB client.

    key = the 64-hex private key that SIGNS orders (not the API-key UUID).
    funder = the proxy wallet address that HOLDS your USDC.
    signature_type distinguishes EOA (0) vs proxy wallets (1 email/magic,
    2 browser-wallet) — funds deposited via polymarket.com live in a proxy, so
    web-app users must use 1 or 2 or orders are rejected.

    Returns the client, or raises. Import is local so the dependency is only
    required for live trading.
    """
    from py_clob_client.client import ClobClient

    client = ClobClient(
        host=config.POLYMARKET_HOST,
        key=config.POLYMARKET_PRIVATE_KEY,
        chain_id=137,
        signature_type=config.POLYMARKET_SIGNATURE_TYPE,
        funder=config.POLYMARKET_FUNDER_ADDRESS or None,
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    return client


def _execute_live(signal: Signal) -> dict:
    """Place a real order via Polymarket CLOB client."""
    try:
        from py_clob_client.clob_types import OrderArgs, OrderType

        client = build_clob_client()

        token_id = get_token_id(signal.market, signal.side)
        if not token_id:
            return _log_and_return(signal, status="error_no_token", order_id=None)

        # Price against the LIVE book, not the stale Gamma mid-price: use the
        # best ask so a BUY is actually marketable, and align to the market's
        # tick size / min order size so the CLOB doesn't reject the order.
        from orderbook import fetch_book
        book = fetch_book(token_id)
        fallback = signal.market.yes_price if signal.side == "YES" else signal.market.no_price
        price = book.best_ask if (book and book.best_ask) else fallback
        if price <= 0 or price >= 1:
            return _log_and_return(signal, status="error_bad_price", order_id=None)

        tick = book.tick_size if book else 0.01
        min_shares = book.min_order_size if book else 5.0
        price = _round_to_tick(price, tick)

        # OrderArgs.size is the number of shares, not USD. shares = usd / price.
        shares = round(signal.bet_amount / price, 2)
        if shares < min_shares:
            return _log_and_return(signal, status="error_below_min_size", order_id=None)

        order_args = OrderArgs(
            price=price,
            size=shares,
            side="BUY",
            token_id=token_id,
        )

        signed_order = client.create_order(order_args)
        resp = client.post_order(signed_order, OrderType.GTC)

        order_id = resp.get("orderID", resp.get("id", "unknown"))
        return _log_and_return(signal, status="executed", order_id=order_id)

    except ImportError:
        return _log_and_return(signal, status="error_no_clob_client", order_id=None)
    except Exception as e:
        return _log_and_return(signal, status=f"error_{type(e).__name__}", order_id=None)


def _log_and_return(signal: Signal, status: str, order_id: str | None) -> dict:
    """Log trade to SQLite and return result dict."""
    trade_id = logger.log_trade(
        market_id=signal.market.condition_id,
        market_question=signal.market.question,
        claude_score=signal.claude_score,
        market_price=signal.market_price,
        edge=signal.edge,
        side=signal.side,
        amount_usd=signal.bet_amount,
        order_id=order_id,
        status=status,
        reasoning=signal.reasoning,
        headlines=signal.headlines,
        news_source=signal.news_source,
        classification=signal.classification,
        materiality=signal.materiality,
        news_latency_ms=signal.news_latency_ms,
        classification_latency_ms=signal.classification_latency_ms,
        total_latency_ms=signal.total_latency_ms,
    )

    return {
        "trade_id": trade_id,
        "market": signal.market.question,
        "side": signal.side,
        "amount": signal.bet_amount,
        "edge": signal.edge,
        "status": status,
        "order_id": order_id,
        "classification": signal.classification,
        "materiality": signal.materiality,
        "latency_ms": signal.total_latency_ms,
    }
