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


def _execute_live(signal: Signal) -> dict:
    """Place a real order via Polymarket CLOB client."""
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType
    except ImportError:
        raise SystemExit(
            "py-clob-client is not installed. "
            "Install it with: pip install py-clob-client>=0.18.0\n"
            "Then set POLYMARKET_API_KEY and POLYMARKET_PRIVATE_KEY in .env"
        )

    try:
        client = _get_clob_client()

        token_id = get_token_id(signal.market, signal.side)
        if not token_id:
            return _log_and_return(signal, status="error_no_token", order_id=None)

        price = signal.market.yes_price if signal.side == "YES" else signal.market.no_price

        order_args = OrderArgs(
            price=price,
            size=signal.bet_amount,
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


def _get_clob_client():
    """Create and authenticate a CLOB client."""
    from py_clob_client.client import ClobClient
    client = ClobClient(
        host=config.POLYMARKET_HOST,
        key=config.POLYMARKET_PRIVATE_KEY,
        chain_id=137,
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    return client


def exit_position(entry_trade: dict, status: str) -> dict:
    """Sell a position to exit. Returns result dict."""
    from py_clob_client.clob_types import OrderArgs, OrderType, BalanceAllowanceParams, AssetType

    try:
        client = _get_clob_client()

        # Get the token_id from the original trade's order
        # We need to look up the token from the market
        trades = client.get_trades()
        token_id = None
        for t in trades:
            if t.get("market") == entry_trade["market_id"]:
                token_id = t.get("asset_id")
                break

        if not token_id:
            return {"status": "error_no_token", "market": entry_trade["market_question"]}

        # Check actual balance
        balance_resp = client.get_balance_allowance(
            params=BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL,
                token_id=token_id,
            )
        )
        balance = float(balance_resp.get("balance", "0"))
        if balance <= 0:
            return {"status": "error_no_balance", "market": entry_trade["market_question"]}

        # Get current sell price
        price_resp = client.get_price(token_id, "SELL")
        sell_price = float(price_resp.get("price", "0"))
        if sell_price <= 0:
            return {"status": "error_no_price", "market": entry_trade["market_question"]}

        order_args = OrderArgs(
            token_id=token_id,
            price=sell_price,
            size=balance,
            side="SELL",
        )

        signed_order = client.create_order(order_args)
        resp = client.post_order(signed_order, OrderType.GTC)
        order_id = resp.get("orderID", resp.get("id", "unknown"))

        exit_id = logger.log_exit_trade(entry_trade, sell_price, status, order_id)

        return {
            "trade_id": exit_id,
            "market": entry_trade["market_question"],
            "side": entry_trade["side"],
            "amount": entry_trade["amount_usd"],
            "entry_price": entry_trade["market_price"],
            "exit_price": sell_price,
            "status": status,
            "order_id": order_id,
        }

    except Exception as e:
        return {
            "status": f"error_{type(e).__name__}",
            "market": entry_trade["market_question"],
            "error": str(e),
        }


async def exit_position_async(entry_trade: dict, status: str) -> dict:
    """Async wrapper around exit_position."""
    return await asyncio.get_event_loop().run_in_executor(
        None, exit_position, entry_trade, status
    )


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

    if trade_id is None:
        return {
            "trade_id": None,
            "market": signal.market.question,
            "side": signal.side,
            "amount": signal.bet_amount,
            "edge": signal.edge,
            "status": "skipped_duplicate",
            "order_id": None,
            "classification": signal.classification,
            "materiality": signal.materiality,
            "latency_ms": signal.total_latency_ms,
        }

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
