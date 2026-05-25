# 📊 주식투자 Agent

ETF 장기투자용 개인 Dashboard. **하루 한 번** 보고 결정하는 워크플로우에 최적화.

- 매일 한국시간 **07:00 KST** 자동 데이터 갱신 (GitHub Actions)
- 4개 탭: 포트폴리오 · 시장 · 시그널 · 뉴스
- 주문은 사용자 본인이 MTS(나무증권 등)로 직접 실행
- LLM API 미사용 · 증권사 API 미사용

---

## 워크플로우

```
06:55  GitHub Actions가 자동 실행
07:00  Dashboard 갱신 완료
07:30  ☕ Dashboard 확인 → 결정
07:40  MTS에서 예약주문 입력
끝.    이후 차트 보지 말 것.
```

---

## 폴더 구조

```
주식투자 Agent/
├── app.py                          # Streamlit Dashboard
├── requirements.txt
├── data/
│   ├── portfolio.csv               # 💡 보유 종목 (수동 입력)
│   ├── watchlist.csv               # 💡 관심 종목
│   ├── target_allocation.json      # 💡 목표 자산배분
│   └── cache/                      # 자동 생성 (수정 금지)
├── src/
│   ├── config.py
│   ├── update.py                   # 매일 실행되는 메인
│   ├── collectors/                 # yfinance · RSS 수집
│   └── analyzers/                  # 시그널 · 리밸런싱
└── .github/workflows/daily-update.yml
```

**사용자가 수정하는 파일은 단 3개**: `portfolio.csv`, `watchlist.csv`, `target_allocation.json`

---

## 로컬 실행

### 1. 가상환경 생성 & 의존성 설치
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. 데이터 최초 수집
```bash
python -m src.update
```
→ `data/cache/` 에 시세, 시장지표, 뉴스, ETF 구성종목이 저장됨.

### 3. Dashboard 실행
```bash
streamlit run app.py
```
→ 브라우저에서 `http://localhost:8501` 열림.

---

## 파일 작성법

### `data/portfolio.csv` (보유 종목)
MTS에서 매수한 후 줄 하나씩 추가/수정.
```csv
ticker,shares,avg_price,currency,purchase_date,note
VOO,10,520.50,USD,2026-05-15,첫 매수
SOXX,3,245.80,USD,2026-05-20,
005930.KS,50,71000,KRW,2026-05-20,삼성전자
```
- `ticker`: 미국은 그냥 심볼(`VOO`, `NVDA`), **한국은 6자리코드+거래소** — 코스피 `.KS`, 코스닥 `.KQ` (예: 삼성전자 `005930.KS`, SK하이닉스 `000660.KS`)
- `shares`: 보유 수량
- `avg_price`: 평균 매수 단가 (**현지통화 기준** — USD 종목은 달러, KRW 종목은 원)
- `currency`: `USD` 또는 `KRW`. 비워두면 티커 접미사로 자동 추론(`.KS`/`.KQ`→KRW)
- 평가금액·비중·손익은 USD로 통일 계산되고, 화면엔 USD/KRW 둘 다 표시됨
- `shares`가 0이면 자동으로 무시됨 (예시 행 용도)

> 💡 **앱 안에서 직접 편집 가능**: 포트폴리오 탭의 **"✏️ 보유 종목 편집"** 을 펼쳐 표를
> 수정하고 **"💾 GitHub에 저장"** 을 누르면 `portfolio.csv` 가 저장소로 커밋됩니다.
> (GitHub 토큰 설정 필요 — 아래 배포 섹션 참고)

### `data/watchlist.csv` (관심 종목)
시그널을 모니터링할 ETF 리스트. 보유 안 해도 됨.

### `data/target_allocation.json` (목표 자산배분)
```json
{
  "allocations": {
    "VOO": 45, "IEF": 20, "IAU": 10,
    "SOXX": 12, "AIQ": 8, "QTUM": 5
  },
  "rebalance_threshold_pct": 5.0
}
```
- 합계 = 100
- `rebalance_threshold_pct`: 목표와 ±N%p 이상 벌어지면 리밸런싱 알림

---

## GitHub & Streamlit Cloud 배포

### GitHub 저장소 생성
1. GitHub에 새 저장소 생성 (private 권장)
2. 이 폴더를 push
3. **Settings → Actions → General → Workflow permissions → "Read and write permissions" 체크** (Actions가 캐시 커밋하려면 필요)

### Streamlit Community Cloud 배포 (무료)
1. https://share.streamlit.io 접속 → GitHub 연동
2. 저장소 선택 → `app.py` 지정
3. 자동 배포됨. 이후 Git push 시 자동 재배포.

### 앱에서 포트폴리오 편집하려면: GitHub 토큰(PAT) 설정
앱의 "보유 종목 편집 → 저장" 기능은 `portfolio.csv` 를 GitHub에 커밋해야 영속화됩니다
(Streamlit Cloud 파일시스템은 임시라 직접 쓰면 사라짐). 그래서 **쓰기 권한 토큰**이 필요합니다.

1. **PAT 발급**: GitHub → Settings → Developer settings → **Personal access tokens → Fine-grained tokens**
   → 이 저장소만 선택 → Repository permissions의 **Contents: Read and write** 부여 → 생성 후 토큰 복사
   (Classic 토큰이면 `repo` 스코프)
2. **Streamlit Secrets에 등록**: 배포된 앱 → 우측 상단 ⋮ → **Settings → Secrets** 에 아래 추가
   ```toml
   GITHUB_TOKEN = "github_pat_xxxxxxxx"
   ```
3. **로컬에서 테스트**하려면 `.streamlit/secrets.toml` 에 같은 줄을 넣거나
   `setx GITHUB_TOKEN "..."` (Windows) 환경변수로 주입. ⚠️ 이 파일은 `.gitignore` 처리되어 커밋되지 않음.

> 토큰이 없으면 편집 기능은 로컬 파일에만 저장(Cloud에선 비영속)하며, 그 외 모든 탭은 정상 동작합니다.

### 자동 갱신 확인
- GitHub 저장소 → Actions 탭 → "Daily Data Update" → 매일 22:00 UTC (= 07:00 KST) 실행 확인
- 수동 실행: Actions 탭 → 워크플로우 선택 → "Run workflow"

---

## 시그널 룰 (참고)

| 신호 | 조건 |
|---|---|
| 🟢 BUY (매수 검토) | 가격 > 200일 이평선 **AND** RSI < 70 |
| 🟡 HOLD (보유) | 그 외 |
| 🔴 SELL (매도 검토) | 가격 < 200일 이평선 **OR** RSI > 80 |

**중요**: 시그널은 보조 지표일 뿐, 자동 매매 신호가 아닙니다. 최종 판단은 본인이.

---

## FAQ

**Q. 한국 ETF도 지원하나요?**
yfinance가 한국 ETF 일부를 지원합니다 (`069500.KS` 등). 다만 미국 ETF가 더 안정적이라 기본 watchlist는 미국 ETF로 구성.

**Q. 잔고 자동 조회는 안 되나요?**
나무증권은 Windows COM 기반 API라 클라우드 자동화가 어렵습니다. ETF는 매매 빈도가 낮아 CSV 수동 관리가 더 효율적.

**Q. LLM 요약을 나중에 추가하려면?**
`src/collectors/news.py` 의 수집 결과를 Groq/Claude 등 LLM API에 전달하는 함수를 추가하면 됩니다. 무료 LLM은 Groq 추천.

---

## ⚠️ 면책 조항

이 도구가 제공하는 모든 정보는 참고용이며 투자 자문이 아닙니다. 투자 결과에 대한 책임은 전적으로 사용자 본인에게 있습니다.
