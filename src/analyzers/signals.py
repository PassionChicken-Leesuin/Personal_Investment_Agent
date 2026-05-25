"""기술적 시그널 - 200일 이평선 + RSI 기반 단순 룰

- 매수 검토 (BUY) : 가격 > 200MA AND RSI < 70
- 매도 검토 (SELL): 가격 < 200MA OR RSI > 80
- 보유 (HOLD)    : 그 외
"""
import pandas as pd
from ta.momentum import RSIIndicator
from src.config import SIGNAL_PARAMS


def compute_signal(df_ticker: pd.DataFrame) -> dict:
    """단일 티커의 일봉 DataFrame을 받아 시그널 dict 반환"""
    df = df_ticker.sort_values("date").reset_index(drop=True)
    if len(df) < SIGNAL_PARAMS["ma_period"]:
        return {
            "signal": "NA",
            "reason": f"데이터 부족 ({len(df)}일 < 200일 필요)",
            "price": float(df["close"].iloc[-1]) if not df.empty else None,
            "ma200": None,
            "rsi": None,
            "score": None,
        }

    close = df["close"]
    ma200 = close.rolling(SIGNAL_PARAMS["ma_period"]).mean()
    rsi_series = RSIIndicator(close=close, window=SIGNAL_PARAMS["rsi_period"]).rsi()

    price = float(close.iloc[-1])
    ma = float(ma200.iloc[-1])
    rsi = float(rsi_series.iloc[-1])

    above_ma = price > ma
    overbought = rsi >= SIGNAL_PARAMS["rsi_overbought"]
    extreme = rsi >= SIGNAL_PARAMS["rsi_extreme"]

    if above_ma and not overbought:
        signal = "BUY"
        reason = f"200일선 위 (+{(price/ma-1)*100:.1f}%) · RSI {rsi:.0f} 과열 아님"
    elif (not above_ma) or extreme:
        signal = "SELL"
        reasons = []
        if not above_ma:
            reasons.append(f"200일선 이탈 ({(price/ma-1)*100:.1f}%)")
        if extreme:
            reasons.append(f"RSI {rsi:.0f} 극단 과열")
        reason = " · ".join(reasons)
    else:
        signal = "HOLD"
        reason = f"200일선 위지만 RSI {rsi:.0f} 과열 구간"

    # 0~100 점수 (단순화)
    ma_dev = (price - ma) / ma * 100  # %
    score = 50 + ma_dev - max(0, (rsi - 50)) * 0.5
    score = max(0, min(100, score))

    return {
        "signal": signal,
        "reason": reason,
        "price": round(price, 4),
        "ma200": round(ma, 4),
        "rsi": round(rsi, 2),
        "score": round(score, 1),
    }


def compute_signals_for_all(prices_df: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        sub = prices_df[prices_df["ticker"] == t]
        sig = compute_signal(sub) if not sub.empty else {
            "signal": "NA", "reason": "데이터 없음",
            "price": None, "ma200": None, "rsi": None, "score": None,
        }
        rows.append({"ticker": t, **sig})
    return pd.DataFrame(rows)
