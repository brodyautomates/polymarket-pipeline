from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import feedparser
import httpx

import config


@dataclass
class NewsItem:
    headline: str
    source: str
    url: str
    published_at: datetime
    summary: str = ""

    def age_hours(self) -> float:
        delta = datetime.now(timezone.utc) - self.published_at
        return delta.total_seconds() / 3600


def scrape_rss(feed_url: str, lookback_hours: int) -> list[NewsItem]:
    """Parse a single RSS feed and return recent items."""
    items = []
    try:
        feed = feedparser.parse(feed_url)
    except Exception:
        return items

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    source_name = feed.feed.get("title", feed_url)

    for entry in feed.entries:
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        else:
            published = datetime.now(timezone.utc)

        if published < cutoff:
            continue

        items.append(NewsItem(
            headline=entry.get("title", "").strip(),
            source=source_name,
            url=entry.get("link", ""),
            published_at=published,
            summary=entry.get("summary", "")[:500],
        ))

    return items


def scrape_newsapi(query: str, lookback_hours: int) -> list[NewsItem]:
    """Pull from NewsAPI.org if key is configured."""
    if not config.NEWSAPI_KEY:
        return []

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    from_dt = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        resp = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": from_dt,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 50,
                "apiKey": config.NEWSAPI_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return items

    for article in data.get("articles", []):
        pub_str = article.get("publishedAt", "")
        try:
            published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            published = datetime.now(timezone.utc)

        items.append(NewsItem(
            headline=article.get("title", "").strip(),
            source=article.get("source", {}).get("name", "NewsAPI"),
            url=article.get("url", ""),
            published_at=published,
            summary=(article.get("description") or "")[:500],
        ))

    return items


def deduplicate(items: list[NewsItem]) -> list[NewsItem]:
    """Remove near-duplicate headlines by normalized prefix matching."""
    seen = set()
    unique = []
    for item in items:
        key = item.headline.lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def scrape_all(lookback_hours: int | None = None) -> list[NewsItem]:
    """Run all scrapers and return deduplicated, sorted results."""
    hours = lookback_hours or config.NEWS_LOOKBACK_HOURS
    all_items = []

    for feed_url in config.RSS_FEEDS:
        all_items.extend(scrape_rss(feed_url, hours))
        time.sleep(0.5)  # polite crawling

    # NewsAPI broad query
    all_items.extend(scrape_newsapi("AI OR artificial intelligence OR crypto OR blockchain", hours))

    unique = deduplicate(all_items)
    unique.sort(key=lambda x: x.published_at, reverse=True)
    return unique


if __name__ == "__main__":
    items = scrape_all()
    print(f"\n--- Scraped {len(items)} unique headlines ---\n")
    for item in items[:20]:
        age = item.age_hours()
        print(f"  [{age:.1f}h ago] [{item.source}] {item.headline}")
