from __future__ import annotations

import config
import logger
from edge import Signal
from markets import get_token_id


def execute_trade(signal: Signal) -> dict:
    """
    Execute a trade on Polymarket or log a dry-run.
    Returns a result dict with order details.
    """
    # Check daily loss limit
    daily_spent = abs(logger.get_daily_pnl())
    if daily_spent + signal.bet_amount > config.DAILY_LOSS_LIMIT_USD:
        return _log_and_return(signal, status="rejected_daily_limit", order_id=None)

    if config.DRY_RUN:
        return _log_and_return(signal, status="dry_run", order_id=None)

    # --- Live execution ---
    return _execute_live(signal)


def _execute_live(signal: Signal) -> dict:
    """Place a real order via Polymarket CLOB client."""
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType

        client = ClobClient(
            host=config.POLYMARKET_HOST,
            key=config.POLYMARKET_API_KEY,
            chain_id=137,  # Polygon mainnet
            funder=config.POLYMARKET_PRIVATE_KEY,
        )

        # Authenticate
        client.set_api_creds(client.create_or_derive_api_creds())

        token_id = get_token_id(signal.market, signal.side)
        if not token_id:
            return _log_and_return(signal, status="error_no_token", order_id=None)

        # Determine price — buy at current market price
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
    )

    return {
        "trade_id": trade_id,
        "market": signal.market.question,
        "side": signal.side,
        "amount": signal.bet_amount,
        "edge": signal.edge,
        "status": status,
        "order_id": order_id,
    }
