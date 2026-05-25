"""포트폴리오 평가 · 리밸런싱 계산

portfolio.csv (수동입력) + 현재가 → 평가금액, 손익, 현재 배분율
target_allocation.json → 목표 vs 현재 괴리 → 리밸런싱 액션 산출
"""
import json
import pandas as pd
from src import config


def infer_currency(ticker: str) -> str:
    """티커 접미사로 통화 추론. 한국 거래소(.KS/.KQ)=KRW, 그 외=USD."""
    t = str(ticker).upper().strip()
    return "KRW" if t.endswith((".KS", ".KQ")) else "USD"


def to_usd_rate(currency: str, usd_krw: float | None) -> float | None:
    """현지통화 → USD 환산 계수. 환율이 없어 KRW 환산이 불가하면 None."""
    c = (currency or "USD").upper()
    if c == "KRW":
        return (1.0 / usd_krw) if usd_krw else None
    return 1.0  # USD 및 미지정 통화는 1:1 취급


def load_portfolio() -> pd.DataFrame:
    df = pd.read_csv(config.PORTFOLIO_CSV)
    # 비어있는 줄(shares==0) 제거
    df = df[df["shares"] > 0].reset_index(drop=True)
    return df


def load_target_allocation() -> dict:
    raw = json.loads(config.TARGET_ALLOC_JSON.read_text(encoding="utf-8"))
    return raw


def evaluate_portfolio(
    portfolio_df: pd.DataFrame,
    current_prices: dict[str, float],
    usd_krw: float | None = None,
) -> pd.DataFrame:
    """평가금액, 손익, 현재 배분 비율 계산.

    가격/단가는 종목의 현지통화(USD 또는 KRW) 기준으로 입력받고,
    합산·비중은 USD로 환산해 통일한다. avg_price/current_price 컬럼은 현지통화 그대로.
    """
    if portfolio_df.empty:
        return pd.DataFrame(columns=[
            "ticker", "currency", "shares", "avg_price", "current_price",
            "cost_usd", "value_usd", "pnl_usd", "pnl_pct",
            "weight_pct", "value_krw",
        ])

    rows = []
    for _, r in portfolio_df.iterrows():
        t = r["ticker"]
        shares = float(r["shares"])
        # 통화: 명시값 우선, 없으면 티커로 추론
        ccy = str(r.get("currency") or "").strip().upper() or infer_currency(t)
        # avg_price 신컬럼 우선, 구 스키마(avg_price_usd) 폴백
        avg = float(r.get("avg_price", r.get("avg_price_usd", 0)) or 0)  # 현지통화
        cur = float(current_prices.get(t, 0) or 0)                       # 현지통화
        rate = to_usd_rate(ccy, usd_krw)
        rate = rate if rate is not None else 0.0  # 환율 없으면 USD 환산 0 (UI에서 경고)
        cost_usd = shares * avg * rate
        value_usd = shares * cur * rate
        pnl_usd = value_usd - cost_usd
        pnl_pct = (pnl_usd / cost_usd * 100) if cost_usd else 0
        rows.append({
            "ticker": t,
            "currency": ccy,
            "shares": shares,
            "avg_price": round(avg, 4),
            "current_price": round(cur, 4),
            "cost_usd": round(cost_usd, 2),
            "value_usd": round(value_usd, 2),
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 2),
        })
    out = pd.DataFrame(rows)
    total = out["value_usd"].sum()
    out["weight_pct"] = (out["value_usd"] / total * 100).round(2) if total else 0
    if usd_krw:
        out["value_krw"] = (out["value_usd"] * usd_krw).round(0)
    return out


def compute_rebalance(
    evaluated: pd.DataFrame,
    target_alloc: dict,
    current_prices: dict[str, float],
    usd_krw: float | None = None,
) -> pd.DataFrame:
    """목표 vs 현재 → 차이 → 주식수 조정 권고 (주식수는 현지통화 가격으로 산출)"""
    targets = target_alloc.get("allocations", {})
    threshold = float(target_alloc.get("rebalance_threshold_pct", 5.0))

    total_value = evaluated["value_usd"].sum() if not evaluated.empty else 0
    held_ccy = (
        dict(zip(evaluated["ticker"], evaluated["currency"]))
        if not evaluated.empty and "currency" in evaluated.columns else {}
    )
    rows = []

    all_tickers = set(targets.keys()) | set(evaluated["ticker"].tolist() if not evaluated.empty else [])
    for t in all_tickers:
        target_pct = float(targets.get(t, 0))
        cur_row = evaluated[evaluated["ticker"] == t] if not evaluated.empty else pd.DataFrame()
        cur_pct = float(cur_row["weight_pct"].iloc[0]) if not cur_row.empty else 0
        cur_value = float(cur_row["value_usd"].iloc[0]) if not cur_row.empty else 0

        target_value = total_value * target_pct / 100       # USD
        diff_value = target_value - cur_value                # USD
        diff_pct_points = target_pct - cur_pct

        ccy = held_ccy.get(t) or infer_currency(t)
        rate = to_usd_rate(ccy, usd_krw)                     # 현지→USD
        price = float(current_prices.get(t, 0) or 0)         # 현지통화 가격
        diff_value_native = (diff_value / rate) if rate else 0
        share_change = (diff_value_native / price) if price else 0

        action = "HOLD"
        if abs(diff_pct_points) >= threshold:
            action = "BUY" if diff_pct_points > 0 else "SELL"

        rows.append({
            "ticker": t,
            "currency": ccy,
            "target_pct": target_pct,
            "current_pct": round(cur_pct, 2),
            "diff_pct_points": round(diff_pct_points, 2),
            "target_value_usd": round(target_value, 2),
            "current_value_usd": round(cur_value, 2),
            "diff_value_usd": round(diff_value, 2),
            "current_price": round(price, 4),
            "share_change_suggest": round(share_change, 2),
            "action": action,
        })

    return pd.DataFrame(rows).sort_values("target_pct", ascending=False).reset_index(drop=True)


def compute_real_exposure(
    evaluated: pd.DataFrame,
    holdings: dict,
) -> pd.DataFrame:
    """ETF 구성종목을 합산하여 '실제로 어떤 회사에 얼마나 노출되어 있는가' 계산"""
    if evaluated.empty:
        return pd.DataFrame(columns=["symbol", "name", "exposure_pct"])

    total_value = evaluated["value_usd"].sum()
    if total_value == 0:
        return pd.DataFrame(columns=["symbol", "name", "exposure_pct"])

    accum: dict[str, dict] = {}
    etfs = holdings.get("etfs", {})
    for _, r in evaluated.iterrows():
        etf_ticker = r["ticker"]
        etf_value = float(r["value_usd"])
        comps = etfs.get(etf_ticker, [])
        for c in comps:
            sym = c["symbol"]
            weight = float(c.get("weight_pct", 0))
            contribution = etf_value * weight / 100
            if sym not in accum:
                accum[sym] = {"name": c.get("name", ""), "value_usd": 0}
            accum[sym]["value_usd"] += contribution
            if c.get("name") and not accum[sym]["name"]:
                accum[sym]["name"] = c["name"]

    rows = [
        {
            "symbol": s,
            "name": v["name"],
            "exposure_value_usd": round(v["value_usd"], 2),
            "exposure_pct": round(v["value_usd"] / total_value * 100, 2),
        }
        for s, v in accum.items()
    ]
    return pd.DataFrame(rows).sort_values("exposure_pct", ascending=False).reset_index(drop=True)
