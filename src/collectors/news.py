"""뉴스 헤드라인 수집 - yfinance .news + Yahoo Finance RSS"""
import json
from datetime import datetime, timezone
import feedparser
import yfinance as yf
from src import config

MAX_PER_TICKER = 5


def fetch_news_for_ticker(ticker: str) -> list[dict]:
    """티커별 헤드라인 수집. yfinance 우선, 실패 시 RSS fallback."""
    items: list[dict] = []

    # 1차: yfinance .news
    try:
        tk = yf.Ticker(ticker)
        for n in (tk.news or [])[:MAX_PER_TICKER]:
            # yfinance 응답 스키마는 변동 잦음 - 방어적으로 파싱
            content = n.get("content") or n
            title = content.get("title") or n.get("title")
            link = (
                (content.get("canonicalUrl") or {}).get("url")
                or (content.get("clickThroughUrl") or {}).get("url")
                or n.get("link")
            )
            publisher = (content.get("provider") or {}).get("displayName") or n.get("publisher", "")
            pub_date = content.get("pubDate") or n.get("providerPublishTime")
            if isinstance(pub_date, (int, float)):
                pub_date = datetime.fromtimestamp(pub_date, tz=timezone.utc).isoformat()
            if title and link:
                items.append({
                    "ticker": ticker,
                    "title": title,
                    "link": link,
                    "publisher": publisher,
                    "published": pub_date,
                    "source": "yfinance",
                })
    except Exception as e:
        print(f"[news] yfinance {ticker} failed: {e}")

    # 2차: Yahoo Finance RSS fallback
    if not items:
        try:
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
            feed = feedparser.parse(url)
            for entry in feed.entries[:MAX_PER_TICKER]:
                items.append({
                    "ticker": ticker,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "publisher": "Yahoo Finance",
                    "published": entry.get("published", ""),
                    "source": "rss",
                })
        except Exception as e:
            print(f"[news] RSS {ticker} failed: {e}")

    return items


def fetch_all_news(tickers: list[str]) -> dict:
    """{ticker: [headline, ...]} 형태로 통합"""
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "items": {t: fetch_news_for_ticker(t) for t in tickers},
    }


def save_news(news: dict) -> None:
    config.NEWS_JSON.write_text(json.dumps(news, indent=2, ensure_ascii=False), encoding="utf-8")


def load_news() -> dict:
    if not config.NEWS_JSON.exists():
        return {"items": {}}
    return json.loads(config.NEWS_JSON.read_text(encoding="utf-8"))
