"""주식투자 Agent Dashboard (Streamlit)

`portfolio.csv` 만 수정하면 모든 탭이 자동 반영됨.
실행: streamlit run app.py
"""
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import config
from src.collectors import prices as price_io
from src.collectors import market as market_io
from src.collectors import news as news_io
from src.collectors import holdings as holdings_io
from src.analyzers import signals as sig_engine
from src.analyzers import portfolio as pf_engine


st.set_page_config(
    page_title="주식투자 Agent",
    page_icon="📊",
    layout="wide",
)


# ─────────────────────────── 데이터 로드 (캐시) ───────────────────────────
@st.cache_data(ttl=300)
def load_all():
    prices_df = price_io.load_prices()
    market_snap = market_io.load_snapshot()
    news = news_io.load_news()
    holdings_data = holdings_io.load_holdings()
    target_alloc = pf_engine.load_target_allocation()
    portfolio_df = pf_engine.load_portfolio()
    watchlist_df = pd.read_csv(config.WATCHLIST_CSV)
    last_update = (
        config.LAST_UPDATE_TXT.read_text(encoding="utf-8").strip()
        if config.LAST_UPDATE_TXT.exists() else "데이터 없음"
    )
    return {
        "prices": prices_df,
        "market": market_snap,
        "news": news,
        "holdings": holdings_data,
        "target": target_alloc,
        "portfolio": portfolio_df,
        "watchlist": watchlist_df,
        "last_update": last_update,
    }


def get_current_prices(prices_df: pd.DataFrame) -> dict[str, float]:
    """가장 최근 종가를 dict로 반환"""
    if prices_df.empty:
        return {}
    latest = prices_df.sort_values("date").groupby("ticker").tail(1)
    return dict(zip(latest["ticker"], latest["close"].astype(float)))


# ─────────────────────────── 사이드바 ───────────────────────────
def render_sidebar(d: dict) -> None:
    st.sidebar.title("📊 주식투자 Agent")
    st.sidebar.markdown(f"**마지막 갱신**\n\n`{d['last_update']}`")
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**사용 방법**\n\n"
        "1. `data/portfolio.csv` 수정\n"
        "2. `data/watchlist.csv` 수정\n"
        "3. `data/target_allocation.json` 수정\n\n"
        "→ 저장하면 Dashboard에 즉시 반영"
    )
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 캐시 비우고 다시 읽기"):
        st.cache_data.clear()
        st.rerun()


# ─────────────────────────── TAB 1: 포트폴리오 ───────────────────────────
def tab_portfolio(d: dict) -> None:
    st.header("💼 포트폴리오")

    portfolio_df = d["portfolio"]
    current_prices = get_current_prices(d["prices"])

    usd_krw = None
    fx = d["market"].get("indicators", {}).get("USD/KRW")
    if fx:
        usd_krw = fx["value"]

    if portfolio_df.empty:
        st.info("`data/portfolio.csv` 에 보유 종목이 없습니다. 매수 후 파일을 갱신하세요.")
        return

    evaluated = pf_engine.evaluate_portfolio(portfolio_df, current_prices, usd_krw)

    # 요약 메트릭
    total_cost = evaluated["cost_usd"].sum()
    total_value = evaluated["value_usd"].sum()
    total_pnl = evaluated["pnl_usd"].sum()
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 평가금액 (USD)", f"${total_value:,.2f}")
    c2.metric("총 손익 (USD)", f"${total_pnl:,.2f}", f"{total_pnl_pct:+.2f}%")
    if usd_krw:
        c3.metric("총 평가금액 (KRW)", f"₩{total_value * usd_krw:,.0f}")
        c4.metric("환율 USD/KRW", f"{usd_krw:,.2f}",
                  f"{fx['change_pct']:+.2f}%")

    st.markdown("### 보유 종목")
    show_cols = ["ticker", "shares", "avg_price_usd", "current_price_usd",
                 "value_usd", "pnl_usd", "pnl_pct", "weight_pct"]
    if "value_krw" in evaluated.columns:
        show_cols.append("value_krw")
    st.dataframe(
        evaluated[show_cols].style.format({
            "avg_price_usd": "${:,.2f}",
            "current_price_usd": "${:,.2f}",
            "value_usd": "${:,.2f}",
            "pnl_usd": "${:,.2f}",
            "pnl_pct": "{:+.2f}%",
            "weight_pct": "{:.2f}%",
            "value_krw": "₩{:,.0f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # 자산배분 파이차트 (목표 vs 현재)
    target_alloc = d["target"]["allocations"]
    st.markdown("### 자산배분: 목표 vs 현재")

    col1, col2 = st.columns(2)
    with col1:
        fig_t = px.pie(
            names=list(target_alloc.keys()),
            values=list(target_alloc.values()),
            title="목표 배분",
            hole=0.4,
        )
        st.plotly_chart(fig_t, use_container_width=True)
    with col2:
        fig_c = px.pie(
            names=evaluated["ticker"],
            values=evaluated["weight_pct"],
            title="현재 배분",
            hole=0.4,
        )
        st.plotly_chart(fig_c, use_container_width=True)

    # 리밸런싱 권고
    st.markdown("### 🔁 리밸런싱 권고")
    rebal = pf_engine.compute_rebalance(evaluated, d["target"], current_prices)
    actionable = rebal[rebal["action"] != "HOLD"]
    if actionable.empty:
        st.success("현재 배분이 목표 범위 내에 있습니다. 별도 조치 불필요.")
    else:
        st.warning(f"{len(actionable)}개 종목이 리밸런싱 임계치(±{d['target']['rebalance_threshold_pct']}%p)를 초과합니다.")
    st.dataframe(
        rebal.style.format({
            "target_pct": "{:.1f}%",
            "current_pct": "{:.2f}%",
            "diff_pct_points": "{:+.2f}",
            "target_value_usd": "${:,.2f}",
            "current_value_usd": "${:,.2f}",
            "diff_value_usd": "${:,.2f}",
            "current_price_usd": "${:,.2f}",
            "share_change_suggest": "{:+.2f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # 실질 노출도
    real_exp = pf_engine.compute_real_exposure(evaluated, d["holdings"])
    if not real_exp.empty:
        st.markdown("### 🔍 실질 노출도 (ETF 구성종목 합산)")
        st.caption("여러 ETF에 같은 종목이 들어있을 때 실제로 어떤 회사에 얼마나 투자되어 있는지")
        st.dataframe(
            real_exp.head(20).style.format({
                "exposure_value_usd": "${:,.2f}",
                "exposure_pct": "{:.2f}%",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ─────────────────────────── TAB 2: 시장 ───────────────────────────
def tab_market(d: dict) -> None:
    st.header("🌍 시장 스냅샷")
    indicators = d["market"].get("indicators", {})
    if not indicators:
        st.info("시장 데이터 없음. `python -m src.update` 를 먼저 실행하세요.")
        return

    cols = st.columns(4)
    for i, (label, info) in enumerate(indicators.items()):
        with cols[i % 4]:
            st.metric(
                label,
                f"{info['value']:,.2f}",
                f"{info['change_pct']:+.2f}%",
            )

    # S&P 500 추이 그래프
    prices_df = d["prices"]
    if not prices_df.empty:
        st.markdown("### 보유/관심 ETF 가격 추이 (1년)")
        watchlist_tickers = d["watchlist"]["ticker"].tolist()
        view = prices_df[prices_df["ticker"].isin(watchlist_tickers)].copy()
        if not view.empty:
            # 시작가=100 정규화
            view = view.sort_values(["ticker", "date"])
            cutoff = view["date"].max() - pd.Timedelta(days=365)
            view = view[view["date"] >= cutoff]
            view["normalized"] = view.groupby("ticker")["close"].transform(
                lambda s: s / s.iloc[0] * 100
            )
            fig = px.line(view, x="date", y="normalized", color="ticker",
                          title="1년 수익률 비교 (시작가=100)")
            fig.update_layout(hovermode="x unified", height=500)
            st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────── TAB 3: 시그널 ───────────────────────────
def tab_signals(d: dict) -> None:
    st.header("📈 매수/매도 시그널")
    st.caption(
        "**룰**: 200일 이평선 + RSI 기반 단순 시그널. "
        "참고용이며, 단정적 추천이 아닙니다."
    )

    watchlist_tickers = d["watchlist"]["ticker"].tolist()
    sig_df = sig_engine.compute_signals_for_all(d["prices"], watchlist_tickers)

    # 색상 매핑
    color_map = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴", "NA": "⚪"}
    sig_df["신호"] = sig_df["signal"].map(color_map) + " " + sig_df["signal"]

    # 표시
    show_df = sig_df[["ticker", "신호", "price", "ma200", "rsi", "score", "reason"]].rename(
        columns={
            "ticker": "티커", "price": "현재가", "ma200": "200일선",
            "rsi": "RSI", "score": "점수(0-100)", "reason": "근거",
        }
    )
    st.dataframe(
        show_df.style.format({
            "현재가": "${:,.2f}",
            "200일선": "${:,.2f}",
            "RSI": "{:.1f}",
            "점수(0-100)": "{:.1f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # 시그널 분포 요약
    counts = sig_df["signal"].value_counts()
    summary = " · ".join(f"{color_map.get(k,'')} {k}: {v}" for k, v in counts.items())
    st.info(f"오늘의 시그널 요약 — {summary}")


# ─────────────────────────── TAB 4: 뉴스 ───────────────────────────
def tab_news(d: dict) -> None:
    st.header("📰 뉴스 헤드라인")
    st.caption("LLM 요약 없음 - 영문 헤드라인 그대로. 클릭하면 원문으로 이동.")

    items = d["news"].get("items", {})
    if not items:
        st.info("뉴스 데이터 없음.")
        return

    tickers = sorted(items.keys())
    selected = st.multiselect("티커 필터", tickers, default=tickers)

    any_shown = False
    for t in selected:
        headlines = items.get(t, [])
        if not headlines:
            continue
        any_shown = True
        st.markdown(f"#### {t}")
        for h in headlines:
            title = h.get("title", "")
            link = h.get("link", "")
            pub = h.get("publisher", "")
            published = h.get("published", "")
            st.markdown(f"- [{title}]({link})  \n  `{pub}` · {published}")

    if not any_shown:
        st.info("선택한 티커에 뉴스가 없습니다.")


# ─────────────────────────── MAIN ───────────────────────────
def main():
    try:
        d = load_all()
    except FileNotFoundError as e:
        st.error(f"필요한 파일이 없습니다: {e}")
        st.code("python -m src.update", language="bash")
        st.stop()

    render_sidebar(d)

    st.title("📊 오늘의 브리핑")
    st.caption(f"마지막 갱신: {d['last_update']}")

    t1, t2, t3, t4 = st.tabs(["💼 포트폴리오", "🌍 시장", "📈 시그널", "📰 뉴스"])
    with t1:
        tab_portfolio(d)
    with t2:
        tab_market(d)
    with t3:
        tab_signals(d)
    with t4:
        tab_news(d)


if __name__ == "__main__":
    main()
