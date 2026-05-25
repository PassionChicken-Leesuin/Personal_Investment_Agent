"""ETF 시세 수집 - 1년치 일봉을 parquet으로 저장"""
import pandas as pd
import yfinance as yf
from src import config


def fetch_prices(tickers: list[str], period: str = "1y") -> pd.DataFrame:
    """
    여러 티커의 1년치 일봉을 long-format DataFrame으로 반환.
    columns: date, ticker, open, high, low, close, volume
    """
    if not tickers:
        return pd.DataFrame()

    raw = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    frames = []
    for t in tickers:
        try:
            if len(tickers) == 1:
                df = raw.copy()
            else:
                df = raw[t].copy()
            df = df.reset_index()
            df.columns = [str(c).lower() for c in df.columns]
            # yfinance 버전에 따라 날짜 인덱스 이름이 "Date"/None 으로 달라짐
            # → reset 후 "date" 또는 "index" 로 들어오므로 통일
            df = df.rename(columns={"index": "date", "datetime": "date"})
            df["ticker"] = t
            frames.append(df[["date", "ticker", "open", "high", "low", "close", "volume"]])
        except Exception as e:
            print(f"[prices] {t} skipped: {e}")

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    return out


def latest_prices(tickers: list[str]) -> dict[str, float]:
    """현재가 dict (실시간 또는 가장 최근 종가)"""
    out = {}
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            info = tk.fast_info
            price = info.get("last_price") or info.get("regular_market_price")
            if price is None:
                hist = tk.history(period="5d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            if price is not None:
                out[t] = float(price)
        except Exception as e:
            print(f"[latest_prices] {t} failed: {e}")
    return out


def save_prices(df: pd.DataFrame) -> None:
    df.to_parquet(config.PRICES_PARQUET, index=False)


def load_prices() -> pd.DataFrame:
    if not config.PRICES_PARQUET.exists():
        return pd.DataFrame()
    return pd.read_parquet(config.PRICES_PARQUET)
