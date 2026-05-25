"""ETF 구성종목 수집 - 실질 노출도 분석용

yfinance는 ETF top holdings를 일부 제공하지만 누락이 잦음.
실패해도 Dashboard는 동작하므로 best-effort로 수집한다.
"""
import json
from datetime import datetime, timezone
import yfinance as yf
from src import config


def fetch_holdings(ticker: str) -> list[dict]:
    """[{symbol, name, weight_pct}, ...] - 가능한 만큼만"""
    try:
        tk = yf.Ticker(ticker)
        funds = getattr(tk, "funds_data", None)
        if funds is None:
            return []
        top = funds.top_holdings  # DataFrame or None
        if top is None or top.empty:
            return []
        items = []
        for sym, row in top.iterrows():
            weight = row.get("Holding Percent") or row.get("holdingPercent") or 0
            name = row.get("Name") or row.get("name") or ""
            items.append({
                "symbol": str(sym),
                "name": str(name),
                "weight_pct": round(float(weight) * 100, 3) if weight < 1 else round(float(weight), 3),
            })
        return items
    except Exception as e:
        print(f"[holdings] {ticker} failed: {e}")
        return []


def fetch_all_holdings(tickers: list[str]) -> dict:
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "etfs": {t: fetch_holdings(t) for t in tickers},
    }


def save_holdings(h: dict) -> None:
    config.HOLDINGS_JSON.write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")


def load_holdings() -> dict:
    if not config.HOLDINGS_JSON.exists():
        return {"etfs": {}}
    return json.loads(config.HOLDINGS_JSON.read_text(encoding="utf-8"))
