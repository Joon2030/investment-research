#!/usr/bin/env python3
"""Weekly Stock Analysis System — runs every Monday at 7am via cron"""

import os
import subprocess
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import yfinance as yf
import anthropic

TICKERS = [
    "QQQ", "NVDA", "AAPL", "MSFT", "TSLA", "GOOGL", "META", "AMZN",
    "005930.KS", "000660.KS",
    # Add your remaining 10 tickers here:
    # "TICKER1", "TICKER2", ...
]

REPORT_DIR = Path.home() / "investment-research" / "reports"
REPO_DIR   = Path.home() / "investment-research"
LOG_DIR    = Path.home() / "investment-research" / "logs"

GMAIL_USER         = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL    = os.environ.get("RECIPIENT_EMAIL", GMAIL_USER)


def collect_stock_data(tickers: list[str]) -> dict:
    stocks = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            hist = t.history(period="1y")
            hist_1w = t.history(period="5d")

            if hist.empty:
                print(f"  [SKIP] No data for {ticker}")
                continue

            current_price  = hist["Close"].iloc[-1]
            week_ago_price = hist_1w["Close"].iloc[0] if len(hist_1w) > 1 else current_price
            week_change_pct = (current_price - week_ago_price) / week_ago_price * 100

            ma50  = hist["Close"].rolling(50).mean().iloc[-1]  if len(hist) >= 50  else None
            ma200 = hist["Close"].rolling(200).mean().iloc[-1] if len(hist) >= 200 else None

            delta = hist["Close"].diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rsi   = (100 - 100 / (1 + gain / loss)).iloc[-1]

            stocks[ticker] = {
                "name":          info.get("shortName", ticker),
                "current_price": round(float(current_price), 2),
                "currency":      info.get("currency", "USD"),
                "week_change_pct": round(week_change_pct, 2),
                "year_high":     round(float(hist["High"].max()), 2),
                "year_low":      round(float(hist["Low"].min()), 2),
                "ma50":          round(float(ma50), 2)  if ma50  is not None else None,
                "ma200":         round(float(ma200), 2) if ma200 is not None else None,
                "above_ma50":    bool(current_price > ma50)  if ma50  is not None else None,
                "above_ma200":   bool(current_price > ma200) if ma200 is not None else None,
                "rsi":           round(float(rsi), 1),
                "pe_ratio":      info.get("trailingPE"),
                "market_cap":    info.get("marketCap"),
                "sector":        info.get("sector", "N/A"),
            }
            print(f"  [OK] {ticker}: ${current_price:.2f} ({week_change_pct:+.2f}%)")
        except Exception as e:
            print(f"  [ERROR] {ticker}: {e}")

    return stocks


def build_data_summary(stocks: dict) -> str:
    date_str = datetime.now().strftime("%Y년 %m월 %d일")
    lines = [f"# 주간 투자 분석 데이터 — {date_str}\n"]
    lines.append("| 티커 | 종목명 | 현재가 | 주간변동 | 52주고/저 | MA50 | MA200 | RSI | PER | 섹터 |")
    lines.append("|------|--------|--------|----------|-----------|------|-------|-----|-----|------|")

    for ticker, s in stocks.items():
        currency = "₩" if s["currency"] == "KRW" else "$"
        price    = f"{currency}{s['current_price']:,.2f}"
        week     = f"{s['week_change_pct']:+.2f}%"
        hi_lo    = f"{currency}{s['year_high']:,.2f} / {currency}{s['year_low']:,.2f}"
        ma50     = f"{currency}{s['ma50']:,.2f} ({'↑' if s['above_ma50'] else '↓'})" if s["ma50"] else "N/A"
        ma200    = f"{currency}{s['ma200']:,.2f} ({'↑' if s['above_ma200'] else '↓'})" if s["ma200"] else "N/A"
        rsi      = f"{s['rsi']:.1f}"
        pe       = f"{s['pe_ratio']:.1f}" if s["pe_ratio"] else "N/A"
        lines.append(f"| {ticker} | {s['name']} | {price} | {week} | {hi_lo} | {ma50} | {ma200} | {rsi} | {pe} | {s['sector']} |")

    return "\n".join(lines)


SYSTEM_PROMPT = """당신은 글로벌 투자 전문 애널리스트입니다. 미국 주식과 한국 주식 모두 분석할 수 있으며, 기술적 분석과 기본적 분석을 결합한 심층 투자 인사이트를 제공합니다.

분석 기준:
- RSI 70 이상: 과매수 구간 (매도 신호)
- RSI 30 이하: 과매도 구간 (매수 신호)
- 주가가 MA50/MA200 위: 강세 신호
- 주가가 MA50/MA200 아래: 약세 신호
- 골든크로스 (MA50 > MA200): 장기 상승 신호
- 데드크로스 (MA50 < MA200): 장기 하락 신호

보고서 형식 (한국어로 작성):
1. **시장 전체 요약** (2-3문장, 이번 주 시장 분위기)
2. **종목별 분석** (각 종목마다: 현황 평가, 기술적 신호, 단기/중기 전망, 투자 의견)
3. **주목할 종목 TOP 3** (매수 관점에서 가장 매력적인 3개 종목 이유와 함께)
4. **주의할 종목** (리스크가 높거나 약세 신호인 종목)
5. **다음 주 핵심 관전 포인트** (주시해야 할 이벤트나 가격 레벨)

투자 의견은 반드시 포함: 적극매수 / 매수 / 중립 / 매도 / 적극매도"""


def analyze_with_claude(data_summary: str) -> str:
    client = anthropic.Anthropic()

    user_message = (
        data_summary
        + "\n\n위 데이터를 바탕으로 각 종목에 대한 상세 분석과 투자 전략을 제시해 주세요. "
        "특히 이번 주 주목할 만한 기술적 신호와 섹터 트렌드를 중심으로 분석해 주세요."
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text


def save_report(stocks: dict, analysis: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    date_str    = datetime.now().strftime("%Y%m%d")
    report_path = REPORT_DIR / f"{date_str}_weekly_report.md"

    data_summary = build_data_summary(stocks)
    content = (
        f"# 주간 투자 분석 리포트\n"
        f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"---\n\n"
        f"## 원시 데이터\n\n"
        f"{data_summary}\n\n"
        f"---\n\n"
        f"## Claude AI 분석\n\n"
        f"{analysis}\n"
    )

    report_path.write_text(content, encoding="utf-8")
    print(f"  [OK] 리포트 저장: {report_path}")
    return report_path


def git_push(report_path: Path):
    try:
        rel_path = report_path.relative_to(REPO_DIR)
        date_str = datetime.now().strftime("%Y-%m-%d")

        subprocess.run(["git", "add", str(rel_path)], cwd=REPO_DIR, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Weekly analysis report {date_str}"],
            cwd=REPO_DIR, check=True,
        )
        result = subprocess.run(
            ["git", "remote"], cwd=REPO_DIR, capture_output=True, text=True
        )
        if "origin" in result.stdout:
            subprocess.run(["git", "push", "origin", "main"], cwd=REPO_DIR, check=True)
            print("  [OK] Git push 완료")
        else:
            print("  [SKIP] 원격 저장소 없음 — 로컬 커밋만 완료")
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Git 오류: {e}")


def build_email_html(stocks: dict, analysis: str) -> str:
    date_str = datetime.now().strftime("%Y년 %m월 %d일")

    # Top movers
    sorted_stocks = sorted(stocks.items(), key=lambda x: x[1]["week_change_pct"], reverse=True)
    top_gainers   = sorted_stocks[:3]
    top_losers    = sorted_stocks[-3:]

    rows = ""
    for ticker, s in stocks.items():
        color  = "#16a34a" if s["week_change_pct"] >= 0 else "#dc2626"
        cur    = "₩" if s["currency"] == "KRW" else "$"
        rsi_color = "#dc2626" if s["rsi"] > 70 else ("#16a34a" if s["rsi"] < 30 else "#374151")
        rows += (
            f"<tr>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #e5e7eb;font-weight:600'>{ticker}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #e5e7eb'>{s['name']}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #e5e7eb'>{cur}{s['current_price']:,.2f}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #e5e7eb;color:{color};font-weight:600'>{s['week_change_pct']:+.2f}%</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #e5e7eb;color:{rsi_color}'>{s['rsi']:.1f}</td>"
            f"</tr>"
        )

    # Convert markdown analysis to simple HTML
    analysis_html = analysis.replace("\n\n", "</p><p>").replace("\n", "<br>")
    analysis_html = f"<p>{analysis_html}</p>"
    analysis_html = analysis_html.replace("**", "<strong>").replace("**", "</strong>")

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#111827;max-width:800px;margin:0 auto;padding:20px">
  <div style="background:linear-gradient(135deg,#1e40af,#7c3aed);padding:24px;border-radius:12px;margin-bottom:24px">
    <h1 style="color:white;margin:0;font-size:24px">📊 주간 투자 분석 리포트</h1>
    <p style="color:#bfdbfe;margin:8px 0 0">{date_str}</p>
  </div>

  <h2 style="color:#1e40af">종목 현황 요약</h2>
  <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">
    <thead>
      <tr style="background:#f3f4f6">
        <th style="padding:10px 8px;text-align:left">티커</th>
        <th style="padding:10px 8px;text-align:left">종목명</th>
        <th style="padding:10px 8px;text-align:left">현재가</th>
        <th style="padding:10px 8px;text-align:left">주간변동</th>
        <th style="padding:10px 8px;text-align:left">RSI</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  <h2 style="color:#1e40af;margin-top:32px">AI 분석 리포트</h2>
  <div style="background:#f9fafb;padding:20px;border-radius:8px;border-left:4px solid #1e40af;line-height:1.7">
    {analysis_html}
  </div>

  <p style="color:#9ca3af;font-size:12px;margin-top:32px;border-top:1px solid #e5e7eb;padding-top:16px">
    이 리포트는 자동으로 생성되었습니다. 투자 결정은 본인 판단 하에 신중하게 내리시기 바랍니다.
  </p>
</body>
</html>
"""


def send_email(stocks: dict, analysis: str):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("  [SKIP] GMAIL_USER 또는 GMAIL_APP_PASSWORD 환경변수 미설정 — 이메일 발송 건너뜀")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 주간 투자 분석 리포트 — {date_str}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = RECIPIENT_EMAIL

    msg.attach(MIMEText(build_email_html(stocks, analysis), "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, RECIPIENT_EMAIL, msg.as_string())
        print(f"  [OK] 이메일 발송 완료 → {RECIPIENT_EMAIL}")
    except Exception as e:
        print(f"  [ERROR] 이메일 발송 실패: {e}")


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"주간 투자 분석 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    print("\n[1/5] 주가 데이터 수집 중...")
    stocks = collect_stock_data(TICKERS)
    if not stocks:
        print("  [ERROR] 데이터를 가져온 종목이 없습니다. 종료합니다.")
        return

    print(f"\n[2/5] Claude AI 분석 중... ({len(stocks)}개 종목)")
    data_summary = build_data_summary(stocks)
    analysis = analyze_with_claude(data_summary)

    print("\n[3/5] 리포트 저장 중...")
    report_path = save_report(stocks, analysis)

    print("\n[4/5] Git 커밋/푸시 중...")
    git_push(report_path)

    print("\n[5/5] 이메일 발송 중...")
    send_email(stocks, analysis)

    print(f"\n{'='*60}")
    print(f"완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
