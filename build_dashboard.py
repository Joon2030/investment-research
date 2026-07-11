#!/usr/bin/env python3
"""
reports/ 폴더의 마크다운(.md) 리포트를 읽어 다크 테마 대시보드(index.html)로 만듭니다.

사용법:
    python3 build_dashboard.py

외부 라이브러리 없이 표준 라이브러리만 사용합니다 (마크다운 변환기 자체 구현).
reports/*.md 파일마다 아래 순서로 제목/날짜/태그/요약을 추출합니다.

  1) 파일 맨 위 "---" YAML 스타일 프런트매터 (선택 사항)
       ---
       title: 삼성전자 실적 분석
       date: 2026-07-10
       tags: [반도체, 실적]
       summary: 한 줄 요약
       ---
  2) 프런트매터가 없으면 본문에서 자동 추출
       - 제목: 첫 번째 "# " 헤딩
       - 날짜: "2026년 07월 01일" 형식 / "생성일시: 2026-05-07" 형식 /
               파일명의 "YYYY-Wnn"(ISO 주차) 또는 "YYYY-MM-DD" 패턴 /
               위 방법으로 못 찾으면 파일 수정시각
       - 태그: 제목 안의 "(AAPL)" 같은 티커, 주간 리포트는 "주간" 태그 자동 추가
       - 요약: 본문 첫 번째 문단
"""

import html
import os
import re
from datetime import date, datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "index.html")

EXCLUDE_NAMES = {"readme.md"}


# ---------------------------------------------------------------------------
# 프런트매터 파싱 (선택 사항)
# ---------------------------------------------------------------------------

def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.group(1), text[m.end():]
    meta = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
        meta[key] = value
    return meta, body


# ---------------------------------------------------------------------------
# 제목 / 날짜 / 태그 / 요약 자동 추출
# ---------------------------------------------------------------------------

KOREAN_DATE_RE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
GENERATED_AT_RE = re.compile(r"생성일시\s*[:：]\s*(\d{4})-(\d{2})-(\d{2})")
ISO_WEEK_RE = re.compile(r"(\d{4})-W(\d{2})")
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
TICKER_RE = re.compile(r"\(([A-Z]{1,6})\)")
PLAIN_STRIP_RE = re.compile(r"[#>*`_\[\]()|-]")


def extract_title(meta, body, filename):
    if meta.get("title"):
        return str(meta["title"])
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    stem = os.path.splitext(filename)[0]
    return stem.replace("_", " ").replace("-", " ").strip()


def extract_date(meta, body, filename, mtime):
    if meta.get("date"):
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(str(meta["date"]), fmt).date()
            except ValueError:
                continue

    head = body[:800]

    m = KOREAN_DATE_RE.search(head)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            pass

    m = GENERATED_AT_RE.search(head)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            pass

    m = ISO_WEEK_RE.search(filename)
    if m:
        y, w = int(m.group(1)), int(m.group(2))
        try:
            return date.fromisocalendar(y, w, 1)
        except ValueError:
            pass

    m = ISO_DATE_RE.search(filename)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            pass

    return date.fromtimestamp(mtime)


def extract_tags(meta, title, filename):
    tags = []
    if meta.get("tags"):
        raw = meta["tags"]
        tags = raw if isinstance(raw, list) else [raw]
    tags = [str(t) for t in tags]
    for t in TICKER_RE.findall(title):
        if t not in tags:
            tags.append(t)
    if ISO_WEEK_RE.search(filename) and "주간" not in tags:
        tags.insert(0, "주간")
    return tags


def extract_summary(meta, body):
    if meta.get("summary"):
        return str(meta["summary"])
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(">") or s.startswith("---") or s.startswith("|"):
            continue
        s = re.sub(r"^\d+\.\s*", "", s)
        s = re.sub(r"^[-*]\s*", "", s)
        s = PLAIN_STRIP_RE.sub("", s).strip()
        if len(s) >= 15:
            return (s[:130] + "…") if len(s) > 130 else s
    return ""


# ---------------------------------------------------------------------------
# 아주 가벼운 마크다운 → HTML 변환기 (외부 의존성 없음)
# ---------------------------------------------------------------------------

def convert_inline(text):
    text = html.escape(text, quote=True)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", r'<img src="\2" alt="\1" loading="lazy">', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def convert_markdown(body):
    lines = body.replace("\r\n", "\n").split("\n")
    out = []
    i, n = 0, len(lines)
    paragraph = []

    def flush_paragraph():
        if paragraph:
            out.append("<p>" + "<br>".join(convert_inline(l) for l in paragraph) + "</p>")
            paragraph.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush_paragraph()
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if m:
            flush_paragraph()
            level = len(m.group(1))
            out.append(f"<h{level}>{convert_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines = []
            while i < n and lines[i].strip().startswith(">"):
                quote_lines.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            out.append("<blockquote><p>" + "<br>".join(convert_inline(l) for l in quote_lines) + "</p></blockquote>")
            continue

        if re.match(r"^\|.+\|$", stripped) and i + 1 < n and re.match(r"^\|?[\s:|-]+\|?$", lines[i + 1].strip()):
            flush_paragraph()
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            align_cells = [c.strip() for c in lines[i + 1].strip().strip("|").split("|")]
            aligns = []
            for c in align_cells:
                left, right = c.startswith(":"), c.endswith(":")
                aligns.append("center" if left and right else "right" if right else "left" if left else "")
            i += 2
            body_rows = []
            while i < n and re.match(r"^\|.+\|$", lines[i].strip()):
                body_rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            thead = "<tr>" + "".join(
                f'<th style="text-align:{aligns[j] or "left"}">{convert_inline(c)}</th>'
                for j, c in enumerate(header_cells)
            ) + "</tr>"
            tbody = ""
            for row in body_rows:
                tbody += "<tr>" + "".join(
                    f'<td style="text-align:{aligns[j] if j < len(aligns) and aligns[j] else "left"}">{convert_inline(c)}</td>'
                    for j, c in enumerate(row)
                ) + "</tr>"
            out.append(f'<div class="table-wrap"><table><thead>{thead}</thead><tbody>{tbody}</tbody></table></div>')
            continue

        m_ul = re.match(r"^(\s*)([-*])\s+(.+)$", line)
        m_ol = re.match(r"^(\s*)(\d+)\.\s+(.+)$", line)
        if m_ul or m_ol:
            flush_paragraph()
            ordered = bool(m_ol)
            items = []
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    # 항목 사이에 빈 줄이 있는 "loose list"도 하나의 목록으로 이어붙인다
                    j = i + 1
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n:
                        nm_ul = re.match(r"^(\s*)([-*])\s+(.+)$", lines[j])
                        nm_ol = re.match(r"^(\s*)(\d+)\.\s+(.+)$", lines[j])
                        if (ordered and nm_ol) or (not ordered and nm_ul):
                            i = j
                            continue
                    break
                cm_ul = re.match(r"^(\s*)([-*])\s+(.+)$", cur)
                cm_ol = re.match(r"^(\s*)(\d+)\.\s+(.+)$", cur)
                if ordered and cm_ol:
                    items.append(cm_ol.group(3))
                elif not ordered and cm_ul:
                    items.append(cm_ul.group(3))
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{convert_inline(it)}</li>" for it in items) + f"</{tag}>")
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        paragraph.append(line.strip())
        i += 1

    flush_paragraph()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 리포트 로드
# ---------------------------------------------------------------------------

def load_reports():
    if not os.path.isdir(REPORTS_DIR):
        return []
    reports = []
    for filename in sorted(os.listdir(REPORTS_DIR)):
        if not filename.lower().endswith(".md"):
            continue
        if filename.lower() in EXCLUDE_NAMES or filename.startswith((".", "_")):
            continue

        path = os.path.join(REPORTS_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()

        meta, body = parse_frontmatter(raw)
        title = extract_title(meta, body, filename)
        report_date = extract_date(meta, body, filename, os.path.getmtime(path))
        tags = extract_tags(meta, title, filename)
        summary = extract_summary(meta, body)
        content_html = convert_markdown(body)
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", os.path.splitext(filename)[0]).strip("-").lower()
        slug = slug or f"report-{len(reports)}"

        reports.append({
            "slug": slug,
            "filename": filename,
            "title": title,
            "date": report_date,
            "tags": tags,
            "summary": summary,
            "html": content_html,
        })

    reports.sort(key=lambda r: r["date"], reverse=True)
    return reports


# ---------------------------------------------------------------------------
# HTML 렌더링
# ---------------------------------------------------------------------------

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>투자 리서치 대시보드</title>
<style>
{css}
</style>
</head>
<body>
<div class="app">
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <span class="brand-mark">IR</span>
        <div class="brand-text">
          <h1>투자 리서치 대시보드</h1>
          <p>{report_count}개 리포트 · 마지막 빌드 {build_time}</p>
        </div>
      </div>
    </div>
  </header>

  <div class="layout">
    <nav class="sidebar" aria-label="리포트 목록">
      <div class="sidebar-scroll">
{sidebar_items}
      </div>
    </nav>

    <main class="main">
{articles}
    </main>
  </div>
</div>

<script>
(function () {{
  var buttons = document.querySelectorAll('.report-item');
  var articles = document.querySelectorAll('.report');

  function selectReport(slug, opts) {{
    opts = opts || {{}};
    buttons.forEach(function (b) {{
      b.classList.toggle('active', b.dataset.slug === slug);
    }});
    articles.forEach(function (a) {{
      a.classList.toggle('active', a.id === 'report-' + slug);
    }});
    if (opts.scroll !== false) {{
      document.querySelector('.main').scrollTo({{ top: 0, behavior: 'auto' }});
    }}
    if (opts.pushHash !== false) {{
      history.replaceState(null, '', '#' + slug);
    }}
  }}

  buttons.forEach(function (b) {{
    b.addEventListener('click', function () {{
      selectReport(b.dataset.slug);
    }});
  }});

  var initial = (location.hash || '').replace('#', '');
  var hasInitial = initial && document.getElementById('report-' + initial);
  if (hasInitial) {{
    selectReport(initial, {{ scroll: false, pushHash: false }});
  }}
}})();
</script>
</body>
</html>
"""

CSS = """
:root {
  --bg: #0b0e14;
  --bg-elevated: #12161f;
  --bg-hover: #191f2c;
  --border: #232838;
  --text: #e6e9f0;
  --text-dim: #8b93a7;
  --accent: #34d399;
  --accent-soft: rgba(52, 211, 153, 0.12);
  --link: #60a5fa;
  --shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--text);
  font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo',
    'Segoe UI', Roboto, 'Malgun Gothic', sans-serif;
  -webkit-font-smoothing: antialiased;
}

.app { min-height: 100vh; display: flex; flex-direction: column; }

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(11, 14, 20, 0.9);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
}
.topbar-inner { max-width: 1400px; margin: 0 auto; padding: 16px 24px; }
.brand { display: flex; align-items: center; gap: 12px; }
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 0.02em;
  flex-shrink: 0;
}
.brand-text h1 { margin: 0; font-size: 17px; font-weight: 700; }
.brand-text p { margin: 2px 0 0; font-size: 12.5px; color: var(--text-dim); }

.layout {
  flex: 1;
  display: grid;
  grid-template-columns: 320px 1fr;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.sidebar {
  border-right: 1px solid var(--border);
  height: calc(100vh - 69px);
  position: sticky;
  top: 69px;
  overflow: hidden;
}
.sidebar-scroll {
  height: 100%;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.report-item {
  display: block;
  width: 100%;
  text-align: left;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-left: 3px solid transparent;
  border-radius: 10px;
  padding: 12px 14px;
  cursor: pointer;
  color: var(--text);
  font-family: inherit;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease;
}
.report-item:hover { background: var(--bg-hover); }
.report-item.active {
  background: var(--accent-soft);
  border-left-color: var(--accent);
}

.report-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.report-date { font-size: 11.5px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.latest-badge {
  font-size: 10.5px;
  font-weight: 700;
  color: var(--accent);
  background: var(--accent-soft);
  padding: 2px 7px;
  border-radius: 999px;
  letter-spacing: 0.02em;
}
.report-item-title {
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.4;
  margin-bottom: 6px;
}
.report-item-summary {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.5;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.report-item-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.tag {
  font-size: 10.5px;
  color: var(--text-dim);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
  padding: 1px 7px;
  border-radius: 999px;
}

.main {
  padding: 32px 40px 80px;
  min-width: 0;
  height: calc(100vh - 69px);
  overflow-y: auto;
}

.report { display: none; max-width: 820px; }
.report.active { display: block; }

.report-header { margin-bottom: 28px; padding-bottom: 20px; border-bottom: 1px solid var(--border); }
.report-header h1 { font-size: 26px; line-height: 1.35; margin: 0 0 12px; }
.report-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.report-meta-date { font-size: 13px; color: var(--text-dim); }

.prose { font-size: 15px; line-height: 1.75; color: var(--text); }
.prose h1, .prose h2, .prose h3, .prose h4 { line-height: 1.4; margin: 32px 0 14px; }
.prose h1 { font-size: 22px; }
.prose h2 { font-size: 19px; padding-top: 4px; border-top: 1px solid var(--border); padding-top: 24px; }
.prose h2:first-child { border-top: none; padding-top: 0; }
.prose h3 { font-size: 16.5px; }
.prose p { margin: 0 0 16px; color: var(--text); }
.prose strong { color: #fff; font-weight: 700; }
.prose em { color: var(--text); }
.prose a { color: var(--link); text-decoration: none; border-bottom: 1px solid rgba(96, 165, 250, 0.35); }
.prose a:hover { border-bottom-color: var(--link); }
.prose ul, .prose ol { margin: 0 0 16px; padding-left: 22px; }
.prose li { margin-bottom: 8px; }
.prose blockquote {
  margin: 0 0 16px;
  padding: 12px 16px;
  border-left: 3px solid var(--accent);
  background: var(--accent-soft);
  border-radius: 0 8px 8px 0;
  color: var(--text-dim);
}
.prose blockquote p { margin: 0; color: var(--text); }
.prose code {
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 6px;
  border-radius: 5px;
  font-size: 0.88em;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
}
.prose pre {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  overflow-x: auto;
  margin: 0 0 16px;
}
.prose pre code { background: none; padding: 0; }
.prose hr { border: none; border-top: 1px solid var(--border); margin: 28px 0; }
.prose img { max-width: 100%; border-radius: 8px; }

.table-wrap { overflow-x: auto; margin: 0 0 20px; border: 1px solid var(--border); border-radius: 10px; }
.prose table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
.prose th, .prose td { padding: 10px 14px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.prose thead th {
  background: var(--bg-elevated);
  color: var(--text-dim);
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.prose tbody tr:last-child td { border-bottom: none; }
.prose tbody tr:hover { background: rgba(255, 255, 255, 0.03); }

.empty-state {
  padding: 60px 24px;
  text-align: center;
  color: var(--text-dim);
}
.empty-state h2 { color: var(--text); margin-bottom: 8px; }

@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .sidebar {
    position: sticky;
    top: 69px;
    height: auto;
    max-height: none;
    border-right: none;
    border-bottom: 1px solid var(--border);
    background: var(--bg);
    z-index: 10;
  }
  .sidebar-scroll {
    flex-direction: row;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 12px 16px;
  }
  .report-item {
    flex: 0 0 240px;
    border-left: 1px solid var(--border);
    border-bottom: 3px solid transparent;
  }
  .report-item.active { border-left: 1px solid var(--border); border-bottom-color: var(--accent); }
  .report-item-summary { -webkit-line-clamp: 3; }
  .main { height: auto; padding: 24px 18px 60px; }
  .report-header h1 { font-size: 21px; }
  .topbar-inner { padding: 14px 18px; }
}
"""


def render_sidebar_item(report, is_latest):
    date_str = report["date"].strftime("%Y.%m.%d")
    badge = '<span class="latest-badge">최신</span>' if is_latest else ""
    tags_html = ""
    if report["tags"]:
        tags_html = '<div class="report-item-tags">' + "".join(
            f'<span class="tag">{html.escape(t)}</span>' for t in report["tags"]
        ) + "</div>"
    summary_html = f'<div class="report-item-summary">{html.escape(report["summary"])}</div>' if report["summary"] else ""
    active_cls = " active" if is_latest else ""
    return f"""      <button class="report-item{active_cls}" data-slug="{report['slug']}" type="button">
        <div class="report-item-top">
          <span class="report-date">{date_str}</span>
          {badge}
        </div>
        <div class="report-item-title">{html.escape(report['title'])}</div>
        {summary_html}{tags_html}
      </button>"""


def render_article(report, is_latest):
    date_str = report["date"].strftime("%Y년 %m월 %d일")
    tags_html = ""
    if report["tags"]:
        tags_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in report["tags"])
    active_cls = " active" if is_latest else ""
    return f"""      <article class="report{active_cls}" id="report-{report['slug']}">
        <header class="report-header">
          <h1>{html.escape(report['title'])}</h1>
          <div class="report-meta">
            <span class="report-meta-date">📅 {date_str}</span>
            {tags_html}
          </div>
        </header>
        <div class="prose">
{report['html']}
        </div>
      </article>"""


def render_html(reports):
    if not reports:
        sidebar_items = '      <div class="empty-state"><h2>리포트 없음</h2><p>reports/ 폴더에 .md 파일을 추가하세요.</p></div>'
        articles = '      <div class="empty-state"><h2>표시할 리포트가 없습니다</h2><p>reports/ 폴더에 마크다운 리포트를 추가한 뒤 다시 빌드하세요.</p></div>'
    else:
        sidebar_items = "\n".join(render_sidebar_item(r, i == 0) for i, r in enumerate(reports))
        articles = "\n".join(render_article(r, i == 0) for i, r in enumerate(reports))

    return PAGE_TEMPLATE.format(
        css=CSS,
        report_count=len(reports),
        build_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        sidebar_items=sidebar_items,
        articles=articles,
    )


def main():
    reports = load_reports()
    output = render_html(reports)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"✅ {len(reports)}개 리포트로 대시보드 생성 완료 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
