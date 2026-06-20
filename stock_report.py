#!/usr/bin/env python3
"""
Stock ticker investment risk report generator.
Usage: python stock_report.py AAPL
       python stock_report.py 005930.KS --output report.md
"""

import argparse
import json
import sys
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    print("yfinance 설치 필요: pip install yfinance")
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("anthropic 설치 필요: pip install anthropic")
    sys.exit(1)


def fetch_stock_data(ticker: str) -> dict:
    stock = yf.Ticker(ticker)

    info = stock.info or {}

    hist = stock.history(period="3mo")
    price_data = {}
    if not hist.empty:
        price_data = {
            "current_price": round(hist["Close"].iloc[-1], 2),
            "3mo_high": round(hist["High"].max(), 2),
            "3mo_low": round(hist["Low"].min(), 2),
            "3mo_return_pct": round(
                (hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0] * 100, 2
            ),
        }

    news = stock.news or []
    recent_news = []
    for item in news[:10]:
        content = item.get("content", {})
        title = content.get("title", "") if isinstance(content, dict) else item.get("title", "")
        summary = content.get("summary", "") if isinstance(content, dict) else item.get("summary", "")
        pub_date = content.get("pubDate", "") if isinstance(content, dict) else item.get("providerPublishTime", "")
        recent_news.append({"title": title, "summary": summary, "date": str(pub_date)})

    financials = {
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "profit_margin": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "roe": info.get("returnOnEquity"),
        "beta": info.get("beta"),
        "dividend_yield": info.get("dividendYield"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
    }

    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName", ticker),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "country": info.get("country", "N/A"),
        "description": info.get("longBusinessSummary", "")[:800],
        "price_data": price_data,
        "financials": financials,
        "news": recent_news,
    }


def generate_report(stock_data: dict) -> str:
    client = anthropic.Anthropic()

    prompt = f"""다음 주식 데이터를 분석하여 투자 리스크 리포트를 한국어로 작성해주세요.

=== 주식 기본 정보 ===
{json.dumps(stock_data, ensure_ascii=False, indent=2)}

=== 리포트 형식 ===
아래 섹션을 포함하여 상세하고 전문적인 투자 분석 리포트를 작성하세요:

1. **회사 개요** - 사업 모델, 섹터, 주요 경쟁력
2. **최근 주가 동향** - 3개월 수익률, 52주 고저가 대비 현재 위치
3. **최근 뉴스 요약** - 주요 이슈와 시장 영향 분석
4. **투자 리스크 분석**
   - 시장 리스크 (베타, 변동성, 거시경제)
   - 재무 리스크 (부채비율, 유동성, 수익성)
   - 사업 리스크 (경쟁, 성장성, 산업 트렌드)
   - 규제/지정학적 리스크
5. **밸류에이션** - PER, 성장률 대비 적정가치 판단
6. **투자 의견 종합** - 리스크/기회 요약 및 투자자 유형별 시사점

전문적이고 객관적인 어조로 작성하며, 구체적인 수치를 활용하여 근거를 제시하세요.
"""

    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=4000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        report_text = ""
        for event in stream:
            if hasattr(event, "type"):
                pass
        final = stream.get_final_message()

    for block in final.content:
        if block.type == "text":
            report_text += block.text

    return report_text


def main():
    parser = argparse.ArgumentParser(description="주식 투자 리스크 리포트 생성기")
    parser.add_argument("ticker", help="주식 티커 심볼 (예: AAPL, TSLA, 005930.KS)")
    parser.add_argument("--output", "-o", help="출력 파일 경로 (예: report.md)")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    print(f"[{ticker}] 데이터 수집 중...", flush=True)

    try:
        stock_data = fetch_stock_data(ticker)
    except Exception as e:
        print(f"데이터 수집 실패: {e}")
        sys.exit(1)

    print(f"[{stock_data['name']}] Claude로 분석 중...", flush=True)

    try:
        report = generate_report(stock_data)
    except Exception as e:
        print(f"리포트 생성 실패: {e}")
        sys.exit(1)

    header = f"# {stock_data['name']} ({ticker}) 투자 리스크 리포트\n생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"
    full_report = header + report

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(full_report)
        print(f"\n리포트 저장 완료: {args.output}")
    else:
        print("\n" + "=" * 60)
        print(full_report)


if __name__ == "__main__":
    main()
