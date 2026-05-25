"""시장 지표 수집 - VIX, 환율, 금리 등"""
import json
from datetime import datetime, timezone
import yfinance as yf
from src import config


def fetch_market_snapshot() -> dict:
    """주요 시장 지표의 현재값 + 전일 대비 변화율"""
    snapshot = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "indicators": {},
    }

    for label, ticker in config.MARKET_TICKERS.items():
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="5d")
            if hist.empty or len(hist) < 2:
                continue
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change_pct = (last - prev) / prev * 100 if prev else 0.0
            snapshot["indicators"][label] = {
                "ticker": ticker,
                "value": round(last, 4),
                "prev": round(prev, 4),
                "change_pct": round(change_pct, 3),
            }
        except Exception as e:
            print(f"[market] {label} ({ticker}) failed: {e}")

    return snapshot


def save_snapshot(snap: dict) -> None:
    config.MARKET_JSON.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")


def load_snapshot() -> dict:
    if not config.MARKET_JSON.exists():
        return {"indicators": {}}
    return json.loads(config.MARKET_JSON.read_text(encoding="utf-8"))
