"""매일 07:00 KST에 실행되는 데이터 갱신 스크립트

GitHub Actions 또는 수동으로 `python -m src.update` 실행.
- watchlist.csv 에 정의된 ETF의 시세/뉴스/구성종목
- 시장 지표 (VIX, 환율, 금리 등)
- portfolio.csv 에 있지만 watchlist 에 없는 티커도 자동 포함
"""
from datetime import datetime, timezone, timedelta
import pandas as pd

from src import config
from src.collectors import prices, market, news, holdings


KST = timezone(timedelta(hours=9))


def collect_target_tickers() -> list[str]:
    """watchlist + portfolio 의 합집합"""
    tickers: set[str] = set()
    if config.WATCHLIST_CSV.exists():
        wl = pd.read_csv(config.WATCHLIST_CSV)
        tickers.update(wl["ticker"].astype(str).str.strip().tolist())
    if config.PORTFOLIO_CSV.exists():
        pf = pd.read_csv(config.PORTFOLIO_CSV)
        pf = pf[pf["shares"] > 0]
        tickers.update(pf["ticker"].astype(str).str.strip().tolist())
    return sorted(tickers)


def run() -> None:
    started = datetime.now(KST)
    print(f"[update] start {started.isoformat()}")

    tickers = collect_target_tickers()
    print(f"[update] tickers: {tickers}")

    # 1) 시세
    print("[update] fetching prices...")
    price_df = prices.fetch_prices(tickers, period="2y")  # 200일선 계산엔 1년+버퍼
    if not price_df.empty:
        prices.save_prices(price_df)
        print(f"[update] prices saved: {len(price_df)} rows")
    else:
        print("[update] prices empty!")

    # 2) 시장 스냅샷
    print("[update] fetching market snapshot...")
    snap = market.fetch_market_snapshot()
    market.save_snapshot(snap)
    print(f"[update] market indicators: {list(snap['indicators'].keys())}")

    # 3) 뉴스
    print("[update] fetching news...")
    n = news.fetch_all_news(tickers)
    news.save_news(n)
    total_items = sum(len(v) for v in n["items"].values())
    print(f"[update] news items: {total_items}")

    # 4) ETF 구성종목 (실패해도 OK)
    print("[update] fetching holdings...")
    h = holdings.fetch_all_holdings(tickers)
    holdings.save_holdings(h)
    non_empty = sum(1 for v in h["etfs"].values() if v)
    print(f"[update] holdings collected for {non_empty}/{len(tickers)} tickers")

    # 5) 갱신 시각 기록
    finished = datetime.now(KST)
    config.LAST_UPDATE_TXT.write_text(finished.isoformat(), encoding="utf-8")
    elapsed = (finished - started).total_seconds()
    print(f"[update] done in {elapsed:.1f}s @ {finished.isoformat()}")


if __name__ == "__main__":
    run()
