"""
Polymarket WebSocket subscriber — live price feed + niche market filtering.
Maintains a live snapshot of tracked markets and detects momentum shifts.
"""
from __future__ import annotations

import asyncio
import json
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import config
from markets import Market, fetch_active_markets, filter_by_categories

log = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    market: Market
    last_price: float
    prev_price: float
    last_update: datetime
    momentum: float = 0.0  # price change per minute

    @property
    def price_change(self) -> float:
        return self.last_price - self.prev_price


class MarketWatcher:
    """Watches niche Polymarket markets via WebSocket + periodic Gamma API refresh."""

    def __init__(self):
        self.snapshots: dict[str, MarketSnapshot] = {}
        self.tracked_markets: list[Market] = []
        self._refresh_interval = 300  # refresh market list every 5 min
        self._ws_connected = False
        self.stats = {
            "ws_messages": 0,
            "price_updates": 0,
            "market_refreshes": 0,
        }

    def get_niche_markets(self, markets: list[Market]) -> list[Market]:
        """Filter to niche markets within volume bounds."""
        return [
            m for m in markets
            if config.MIN_VOLUME_USD <= m.volume <= config.MAX_VOLUME_USD
            and m.active
        ]

    async def refresh_markets(self):
        """Fetch and filter markets from Gamma API."""
        try:
            all_markets = await asyncio.get_event_loop().run_in_executor(
                None, lambda: fetch_active_markets(limit=200)
            )
            categorized = filter_by_categories(all_markets)
            self.tracked_markets = self.get_niche_markets(categorized)

            # Update snapshots
            now = datetime.now(timezone.utc)
            existing_ids = set(self.snapshots.keys())
            new_ids = set()

            for m in self.tracked_markets:
                new_ids.add(m.condition_id)
                if m.condition_id not in self.snapshots:
                    self.snapshots[m.condition_id] = MarketSnapshot(
                        market=m,
                        last_price=m.yes_price,
                        prev_price=m.yes_price,
                        last_update=now,
                    )
                else:
                    snap = self.snapshots[m.condition_id]
                    snap.market = m  # update metadata

            # Remove stale snapshots
            for stale_id in existing_ids - new_ids:
                del self.snapshots[stale_id]

            self.stats["market_refreshes"] += 1
            log.info(f"[watcher] Tracking {len(self.tracked_markets)} niche markets")

        except Exception as e:
            log.warning(f"[watcher] Market refresh error: {e}")

    async def _connect_websocket(self):
        """Connect to Polymarket WebSocket for live price updates."""
        try:
            import websockets
        except ImportError:
            log.warning("[watcher] websockets not installed — using polling fallback")
            return

        ws_backoff = 5

        while True:
            try:
                async with websockets.connect(config.POLYMARKET_WS_HOST) as ws:
                    self._ws_connected = True
                    ws_backoff = 5  # reset on successful connect
                    log.info("[watcher] WebSocket connected")

                    # Subscribe to tracked markets
                    for market in self.tracked_markets:
                        for token in market.tokens:
                            tid = token.get("token_id")
                            if tid:
                                sub = {"type": "subscribe", "channel": "price", "market": tid}
                                await ws.send(json.dumps(sub))

                    # Listen for updates
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=10)
                            self.stats["ws_messages"] += 1
                            if not isinstance(msg, str) or not msg.strip():
                                log.debug(f"[watcher] Non-text/empty WS frame, skipping")
                                continue
                            try:
                                data = json.loads(msg)
                            except json.JSONDecodeError:
                                log.debug(f"[watcher] Non-JSON WS message: {msg[:200]}")
                                continue
                            self._handle_ws_message(data)
                        except asyncio.TimeoutError:
                            # Send ping
                            await ws.ping()

            except Exception as e:
                self._ws_connected = False
                log.warning(f"[watcher] WebSocket error: {e}, reconnecting in {ws_backoff}s")
                await asyncio.sleep(ws_backoff)
                ws_backoff = min(ws_backoff * 2, 60)  # cap at 60s

    def _handle_ws_message(self, data: dict):
        """Process a WebSocket price update."""
        msg_type = data.get("type", "")
        if msg_type not in ("price_change", "last_trade_price"):
            return

        market_id = data.get("market", data.get("condition_id", ""))
        price = data.get("price")

        if not market_id or price is None:
            return

        # Find matching snapshot
        for cid, snap in self.snapshots.items():
            token_ids = [t.get("token_id", "") for t in snap.market.tokens]
            if market_id in token_ids or market_id == cid:
                now = datetime.now(timezone.utc)
                elapsed = (now - snap.last_update).total_seconds()
                snap.prev_price = snap.last_price
                snap.last_price = float(price)
                snap.last_update = now
                if elapsed > 0:
                    snap.momentum = (snap.last_price - snap.prev_price) / (elapsed / 60)
                self.stats["price_updates"] += 1
                break

    async def _polling_fallback(self):
        """Poll Gamma API for price updates when WebSocket unavailable."""
        while True:
            await asyncio.sleep(30)
            if self._ws_connected:
                continue
            await self.refresh_markets()

    async def run(self):
        """Start the market watcher — refresh + WebSocket + polling fallback."""
        await self.refresh_markets()

        async def refresh_loop():
            while True:
                await asyncio.sleep(self._refresh_interval)
                await self.refresh_markets()

        await asyncio.gather(
            refresh_loop(),
            self._connect_websocket(),
            self._polling_fallback(),
            return_exceptions=True,
        )

    def get_market_by_question(self, question_fragment: str) -> Market | None:
        """Find a tracked market by partial question match."""
        frag = question_fragment.lower()
        for m in self.tracked_markets:
            if frag in m.question.lower():
                return m
        return None

    def get_snapshot(self, condition_id: str) -> MarketSnapshot | None:
        return self.snapshots.get(condition_id)


if __name__ == "__main__":
    async def _test():
        watcher = MarketWatcher()
        await watcher.refresh_markets()
        print(f"Tracking {len(watcher.tracked_markets)} niche markets:")
        for m in watcher.tracked_markets[:10]:
            print(f"  [{m.category}] ${m.volume:,.0f} | YES:{m.yes_price:.2f} | {m.question[:60]}")

    asyncio.run(_test())
