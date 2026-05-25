"""중앙 설정 - 모든 모듈이 참조하는 경로/상수"""
from pathlib import Path

# 프로젝트 루트
ROOT = Path(__file__).resolve().parent.parent

# 입력 데이터 (사용자가 수정)
DATA_DIR = ROOT / "data"
PORTFOLIO_CSV = DATA_DIR / "portfolio.csv"
WATCHLIST_CSV = DATA_DIR / "watchlist.csv"
TARGET_ALLOC_JSON = DATA_DIR / "target_allocation.json"

# 자동 생성 캐시 (07:00 KST 갱신물)
CACHE_DIR = DATA_DIR / "cache"
PRICES_PARQUET = CACHE_DIR / "prices.parquet"          # 1년치 일봉
MARKET_JSON = CACHE_DIR / "market_snapshot.json"        # 환율/VIX/금리 등
NEWS_JSON = CACHE_DIR / "news.json"                     # 헤드라인 리스트
HOLDINGS_JSON = CACHE_DIR / "etf_holdings.json"         # ETF 구성종목
LAST_UPDATE_TXT = CACHE_DIR / "last_update.txt"         # 마지막 갱신 시각

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 시장 지표 티커
MARKET_TICKERS = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "KOSPI": "^KS11",
    "VIX": "^VIX",
    "10Y Treasury": "^TNX",
    "USD/KRW": "KRW=X",
    "Gold": "GC=F",
    "WTI Oil": "CL=F",
}

# 시그널 룰 파라미터
SIGNAL_PARAMS = {
    "ma_period": 200,        # 장기 추세선
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_extreme": 80,
}
