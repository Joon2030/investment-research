#!/usr/bin/env python3
"""
나스닥100 상위 20개 종목 주간 자동 분석 리포트 생성기
사용법: python weekly_report.py
필요: ANTHROPIC_API_KEY 환경변수, yfinance, anthropic, pandas
"""

import os
import sys
import json
from datetime import date

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance 설치 필요: pip install yfinance")

try:
    import anthropic
except ImportError:
    sys.exit("anthropic 설치 필요: pip install anthropic")


TICKERS = [
    "MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO",
    "COST", "NFLX", "ASML", "AMD", "QCOM", "INTU", "TXN", "ISRG", "AMGN", "PEP", "ADBE",
]

REPORT_DIR = os.path.expanduser("~/investment-research/reports")


def get_week_label():
    iso = date.today().isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def safe_round(val, decimals=2):
    try:
        return round(float(val), decimals)
    except (TypeError, ValueError):
        return None


def fetch_stock_data():
    print("📊 주가 데이터 수집 중...", flush=True)

    # 20개 종목 가격 히스토리 한번에 다운로드 (주간 변화율 계산용)
    prices_df = None
    try:
        raw = yf.download(
            " ".join(TICKERS), period="3mo", progress=False, auto_adjust=True
        )
        # yfinance 0.2.x: raw.columns는 MultiIndex (Price, Ticker)
        # raw["Close"]는 Ticker를 컬럼으로 갖는 DataFrame
        prices_df = raw["Close"]
    except Exception as e:
        print(f"  가격 일괄 다운로드 실패: {e}", file=sys.stderr)

    stocks = {}

    for ticker in TICKERS:
        print(f"  {ticker}...", end="", flush=True)
        try:
            info = yf.Ticker(ticker).info or {}

            current_price = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )
            market_cap = info.get("marketCap")
            pe = info.get("trailingPE") or info.get("forwardPE")
            week52_high = info.get("fiftyTwoWeekHigh")
            week52_low = info.get("fiftyTwoWeekLow")
            div_yield = info.get("dividendYield")
            revenue_growth = info.get("revenueGrowth")

            # 52주 고점 대비 괴리율
            pct_from_high = None
            if current_price and week52_high:
                pct_from_high = safe_round(
                    (current_price / week52_high - 1) * 100, 1
                )

            # 주간 변화율 (최근 5거래일)
            week_change = None
            if prices_df is not None and ticker in prices_df.columns:
                series = prices_df[ticker].dropna()
                if len(series) >= 6:
                    week_change = safe_round(
                        (series.iloc[-1] / series.iloc[-6] - 1) * 100, 2
                    )

            stocks[ticker] = {
                "name": info.get("longName") or info.get("shortName") or ticker,
                "sector": info.get("sector", "N/A"),
                "price_usd": safe_round(current_price, 2),
                "market_cap_b": safe_round(market_cap / 1e9, 1) if market_cap else None,
                "per": safe_round(pe, 1),
                "pbr": safe_round(info.get("priceToBook"), 2),
                "beta": safe_round(info.get("beta"), 2),
                "w52_high": safe_round(week52_high, 2),
                "w52_low": safe_round(week52_low, 2),
                "pct_from_52w_high": pct_from_high,
                "week_change_pct": week_change,
                "div_yield_pct": safe_round(div_yield * 100, 2) if div_yield else 0,
                "revenue_growth_pct": (
                    safe_round(revenue_growth * 100, 1) if revenue_growth else None
                ),
            }
            print(" ✓", flush=True)

        except Exception as e:
            print(f" ✗ ({e})", file=sys.stderr)
            stocks[ticker] = {"name": ticker, "error": str(e)}

    return stocks


def generate_report(stocks, week_label):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("오류: ANTHROPIC_API_KEY 환경변수를 설정해주세요.")

    client = anthropic.Anthropic(api_key=api_key)
    today_str = date.today().strftime("%Y년 %m월 %d일")
    stocks_json = json.dumps(stocks, ensure_ascii=False, indent=2)

    prompt = f"""당신은 전문 주식 애널리스트입니다. 나스닥100 상위 20개 종목의 이번 주 시장 데이터를 분석하여 한국어 주간 투자 리포트를 작성해 주세요.

**분석 기준일:** {today_str} ({week_label})

**종목 데이터 (JSON):**
```json
{stocks_json}
```

**필드 안내:**
- price_usd: 현재 주가(USD)
- market_cap_b: 시가총액(십억 달러)
- per: 주가수익비율 (후행 또는 선행)
- pbr: 주가순자산비율
- beta: 시장 대비 변동성 (1.0 = 시장과 동일)
- w52_high / w52_low: 52주 최고가 / 최저가
- pct_from_52w_high: 52주 고점 대비 현재가 괴리율(%)
- week_change_pct: 최근 5거래일 주가 등락률(%)
- div_yield_pct: 배당수익률(%)
- revenue_growth_pct: 전년 대비 매출 성장률(%)
- null 값은 데이터 미수집을 의미함

---

아래 형식을 **그대로** 사용하여 마크다운 리포트를 작성해 주세요. 섹션 제목을 바꾸지 마세요.

# 나스닥100 주간 투자 리포트 — {week_label}

> **분석일:** {today_str} | 대상: 나스닥100 상위 20개 종목

---

## 📌 주간 핵심 이슈 TOP 5

이번 주 데이터에서 도출되는 핵심 투자 이슈 5가지를 번호 목록으로 작성하세요.
각 이슈는: **이슈 제목** 형태로 시작하고, 관련 종목·수치 근거·투자 시사점을 포함하세요.

## 📋 종목별 한줄 요약

20개 종목 각각을 다음 형식으로 작성하세요:
- **TICKER (회사명)**: 현황 및 투자 관점 한줄 요약

## 📊 밸류에이션 비교표

시가총액 내림차순으로 정렬하여 아래 마크다운 테이블을 완성하세요.
null 값은 N/A로 표시하고, 숫자는 실제 데이터를 사용하세요.

| 종목 | 현재가($) | 주간등락(%) | 시총(B$) | PER | PBR | 베타 | 52주고점比(%) |
|:-----|----------:|------------:|--------:|----:|----:|-----:|--------------:|

## 💡 주간 총평

이번 주 전반적인 시장 흐름, 섹터별 동향, 다음 주 주목해야 할 포인트를 2~3문단으로 서술하세요.

---
*본 리포트는 AI 자동 분석으로 생성되었으며, 투자 권유가 아닙니다.*
"""

    print(f"\n🤖 Claude API 분석 중 (1회 호출)...\n", flush=True)
    print("=" * 70, flush=True)

    # 스트리밍으로 실시간 출력하면서 최종 텍스트 수집
    with client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=16000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        report_parts = []
        for text in stream.text_stream:
            print(text, end="", flush=True)
            report_parts.append(text)

        final = stream.get_final_message()

    print("\n" + "=" * 70, flush=True)
    print(
        f"\n💰 토큰 사용: 입력 {final.usage.input_tokens:,} / 출력 {final.usage.output_tokens:,}",
        flush=True,
    )

    return "".join(report_parts)


def main():
    week_label = get_week_label()
    print(f"🚀 나스닥100 주간 리포트 생성 시작: {week_label}\n", flush=True)

    # 1단계: yfinance로 20개 종목 데이터 수집
    stocks = fetch_stock_data()

    # 2단계: Claude API 1회 호출로 전체 분석
    report = generate_report(stocks, week_label)

    # 3단계: 리포트 저장
    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = os.path.join(REPORT_DIR, f"{week_label}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n✅ 리포트 저장 완료: {out_path}", flush=True)


if __name__ == "__main__":
    main()
