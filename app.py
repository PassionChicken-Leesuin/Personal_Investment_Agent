"""주식투자 Agent Dashboard (Streamlit)

`portfolio.csv` 는 앱 안에서 직접 편집 → GitHub 커밋 가능 (Secrets에 토큰 필요).
실행: streamlit run app.py
"""
import os
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import config
from src import github_io
from src import update as update_job
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
    with st.sidebar:
        st.title("📊 주식투자 Agent")
        st.markdown(f"**마지막 갱신**\n\n`{d['last_update']}`")
        st.markdown("---")
        if st.button("🔄 지금 갱신", type="primary", use_container_width=True):
            try:
                with st.spinner("최신 데이터 받는 중... (yfinance)"):
                    update_job.run()  # 현재 시각 기준으로 재수집
                st.cache_data.clear()
                st.toast("갱신 완료!", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"갱신 실패: {e}")
        st.caption("매일 07:00 KST 자동 갱신 + 위 버튼으로 즉시 갱신")


# ─────────────────────────── 포트폴리오 편집 (인앱 → GitHub 커밋) ───────────────────────────
def _get_github_token() -> str | None:
    """Streamlit Secrets 또는 환경변수에서 GitHub 토큰을 읽는다 (없으면 None)."""
    try:
        if "GITHUB_TOKEN" in st.secrets:
            return st.secrets["GITHUB_TOKEN"]
    except Exception:
        pass  # secrets.toml 자체가 없을 때
    return os.environ.get("GITHUB_TOKEN")


def render_portfolio_editor() -> None:
    """보유 종목을 표로 편집하고 GitHub(또는 로컬)에 저장한다."""
    with st.expander("✏️ 보유 종목 편집", expanded=False):
        st.caption(
            "표를 직접 수정하세요. `shares`/`avg_price`/`currency` 만 정확하면 됩니다. "
            "한국 주식은 티커에 `.KS`(코스피)·`.KQ`(코스닥)를 붙이고 통화를 `KRW`로. "
            "예: 삼성전자 `005930.KS`. 저장하면 `data/portfolio.csv` 로 커밋됩니다."
        )
        raw = pd.read_csv(config.PORTFOLIO_CSV)  # 0주 예시 포함 전체
        # 구 스키마(avg_price_usd / currency 없음) 호환 정규화
        if "avg_price" not in raw.columns and "avg_price_usd" in raw.columns:
            raw = raw.rename(columns={"avg_price_usd": "avg_price"})
        if "currency" not in raw.columns:
            raw["currency"] = raw["ticker"].map(pf_engine.infer_currency)
        edited = st.data_editor(
            raw,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="portfolio_editor",
            column_config={
                "ticker": st.column_config.TextColumn("티커", required=True, help="미국: VOO / 한국: 005930.KS"),
                "shares": st.column_config.NumberColumn("수량", min_value=0, step=1),
                "avg_price": st.column_config.NumberColumn("평균단가(현지통화)", min_value=0.0, format="%.2f"),
                "currency": st.column_config.SelectboxColumn("통화", options=["USD", "KRW"], default="USD"),
                "purchase_date": st.column_config.TextColumn("매수일"),
                "note": st.column_config.TextColumn("메모"),
            },
        )

        token = _get_github_token()
        col_a, col_b = st.columns([1, 3])
        save = col_a.button("💾 GitHub에 저장", type="primary", use_container_width=True)
        if token:
            col_b.caption("토큰 감지됨 → GitHub 저장소로 커밋됩니다.")
        else:
            col_b.caption("⚠️ GitHub 토큰 없음 → 로컬 파일에만 저장(Cloud에선 비영속). Secrets에 `GITHUB_TOKEN` 추가 필요.")

        if not save:
            return

        # ticker 비어있는 행 제거 후 CSV 직렬화
        clean = edited.dropna(subset=["ticker"]).copy()
        clean = clean[clean["ticker"].astype(str).str.strip() != ""]
        csv_str = clean.to_csv(index=False)

        if token:
            try:
                github_io.commit_text_file(
                    token=token,
                    repo=config.GITHUB_REPO,
                    path=config.PORTFOLIO_REPO_PATH,
                    content=csv_str,
                    message="chore: update portfolio via dashboard",
                    branch=config.GITHUB_BRANCH,
                )
            except Exception as e:
                st.error(f"GitHub 저장 실패: {e}")
                return
            # 현재 세션에도 즉시 반영(Cloud 재배포 전까지)
            config.PORTFOLIO_CSV.write_text(csv_str, encoding="utf-8")
            st.success("GitHub에 커밋했습니다. 화면을 갱신합니다. (Cloud는 곧 자동 재배포)")
        else:
            config.PORTFOLIO_CSV.write_text(csv_str, encoding="utf-8")
            st.success("로컬 파일에 저장했습니다. (GitHub 토큰이 없어 커밋은 생략)")

        st.cache_data.clear()
        st.rerun()


# ─────────────────────────── TAB 1: 포트폴리오 ───────────────────────────
def tab_portfolio(d: dict) -> None:
    st.header("💼 포트폴리오")
    render_portfolio_editor()
    st.markdown("---")

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

    if (evaluated["currency"] == "KRW").any() and not usd_krw:
        st.warning("KRW 보유 종목이 있는데 USD/KRW 환율 데이터가 없어 환산이 부정확합니다. "
                   "사이드바의 '🔄 지금 갱신' 으로 환율을 받아오세요.")

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
    st.caption("`평균단가`·`현재가`는 종목의 현지통화 기준입니다 (통화 열 참고). 평가·비중·손익은 USD로 통일.")
    show_cols = ["ticker", "currency", "shares", "avg_price", "current_price",
                 "value_usd", "pnl_usd", "pnl_pct", "weight_pct"]
    if "value_krw" in evaluated.columns:
        show_cols.append("value_krw")
    st.dataframe(
        evaluated[show_cols].rename(columns={
            "ticker": "티커", "currency": "통화", "shares": "수량",
            "avg_price": "평균단가", "current_price": "현재가",
        }).style.format({
            "평균단가": "{:,.2f}",
            "현재가": "{:,.2f}",
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
    rebal = pf_engine.compute_rebalance(evaluated, d["target"], current_prices, usd_krw)
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
            "current_price": "{:,.2f}",
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
