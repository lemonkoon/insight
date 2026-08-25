"""
경쟁사 레이더 - 2단계: HTML 카드 렌더링
data/raw/*.json (최근 30일치) 을 모두 읽어서 site/index.html 정적 페이지 1개로 만든다.
날짜 탭 전환은 클라이언트 JS로 처리(서버/재요청 없이 전 날짜 데이터를 페이지에 미리 내장).
지금 단계는 '레이아웃 확인용' — 중요도 배지는 아직 간단한 키워드 룰 기반(AI 미사용).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
ENRICH_DIR = ROOT / "data" / "enrich"
BIDS_DIR = ROOT / "data" / "bids"
SITE_DIR = ROOT / "site"

MAX_DAYS = 30

HIGH_KEYWORDS = ["출시", "수주", "계약", "투자", "인수", "점유율", "1위", "특허", "인증", "제휴", "MOU", "상장"]

STOPWORDS = {"제니우스", "브레인즈컴퍼니", "로그프레소", "파이오링크", "와탭랩스", "이글루코퍼레이션",
             "Logpresso", "PIOLINK", "WhaTap", "위해", "통해", "관련", "가운데", "이번"}


def badge_for(item: dict) -> str:
    if not item.get("recent"):
        return "low"
    title = item.get("title", "")
    if any(k in title for k in HIGH_KEYWORDS):
        return "high"
    return "mid"


def extract_keywords(all_recent_titles, top_n=6):
    words = []
    for t in all_recent_titles:
        for w in re.split(r"[\s,.'\"·…\-\[\]()]+", t):
            w = w.strip()
            if len(w) >= 2 and w not in STOPWORDS and not w.isdigit():
                words.append(w)
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: -x[1])
    return [w for w, _ in ranked[:top_n]]


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_item_card(item: dict, translated_title: str = None) -> str:
    badge = badge_for(item)
    date_str = item["pubDate"][:10]
    main_title = esc(translated_title) if translated_title else esc(item["title"])
    orig_line = f'<div class="item-title-orig">{esc(item["title"])}</div>' if translated_title else ""
    return f"""
        <a class="item-card badge-{badge}" href="{esc(item['link'])}" target="_blank" rel="noopener">
          <div class="item-title">{main_title}</div>
          {orig_line}
          <div class="item-meta">{esc(item['source'])} · {date_str}{' · 최근 소식' if item.get('recent') else ''}</div>
        </a>"""


def render_company_section(company: dict) -> str:
    """최근(48h) 소식이 있으면 카드로, 없으면 빈 문자열(호출부에서 대체 문구 처리)."""
    items = company["items"]
    if isinstance(items, dict) and "error" in items:
        return ""

    recent_items = [i for i in items if i.get("recent")]
    if not recent_items:
        return ""

    shown = recent_items[:4]
    overall_badge = max((badge_for(i) for i in shown), key=lambda b: {"high": 2, "mid": 1, "low": 0}[b])
    body = "".join(render_item_card(i) for i in shown)

    return f"""
      <section class="company-card stripe-{overall_badge}">
        <div class="company-head">
          <span class="company-name">{esc(company['name'])}</span>
          <span class="company-cat">{esc(company.get('category', ''))}</span>
          <span class="badge-pill badge-{overall_badge}">{overall_badge.upper()}</span>
        </div>
        <div class="company-body">{body}</div>
      </section>"""


def render_own_section(own: dict) -> str:
    """자사(티사이언티픽) 카드. 경쟁사 중요도 배지와 헷갈리지 않도록 별도 스타일(자사=파란색)."""
    items = own["items"]
    if isinstance(items, dict) and "error" in items:
        return ""

    recent_items = [i for i in items if i.get("recent")]
    if not recent_items:
        return ""

    shown = recent_items[:4]
    body = "".join(render_item_card(i) for i in shown)

    return f"""
      <section class="company-card stripe-own">
        <div class="company-head">
          <span class="company-name">{esc(own['name'])}</span>
          <span class="company-cat">자사</span>
          <span class="badge-pill badge-own">자사</span>
        </div>
        <div class="company-body">{body}</div>
      </section>"""


def render_global_section(g: dict, enrich_map: dict) -> str:
    items = g["items"]
    recent_items = [i for i in items if i.get("recent")] if isinstance(items, list) else []
    if not recent_items:
        return ""
    shown = recent_items[:2]
    cards = ""
    why_lines = []
    for i in shown:
        e = enrich_map.get(i["link"], {})
        cards += render_item_card(i, translated_title=e.get("title_ko"))
        if e.get("why"):
            why_lines.append(e["why"])
    if why_lines:
        why_html = "".join(f'<div class="why-line">※ 왜 중요한가: {esc(w)}</div>' for w in why_lines)
    else:
        why_html = '<div class="why-line">※ 왜 중요한가: (다음 자동 갱신 때 채워질 예정)</div>'
    return f"""
      <section class="company-card stripe-mid">
        <div class="company-head">
          <span class="company-name">{esc(g['name'])}</span>
          <span class="badge-pill badge-mid">참고</span>
        </div>
        <div class="company-body">{cards}</div>
        {why_html}
      </section>"""


def render_bid_card(bid: dict) -> str:
    return f"""
        <a class="item-card badge-mid" href="{esc(bid['link'])}" target="_blank" rel="noopener">
          <div class="item-title">{esc(bid['title'])}</div>
          <div class="item-meta">{esc(bid['org'])} · 마감 {esc(bid['close_date'])} · #{esc(bid['matched_keyword'])}</div>
        </a>"""


def load_bids(date: str) -> list:
    path = BIDS_DIR / f"{date}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("bids", [])
    except (json.JSONDecodeError, OSError):
        return []


def render_bids_section(bids: list) -> str:
    if not bids:
        return '<div class="empty">최근 24시간 내 관련 입찰공고 없음</div>'
    cards = "".join(render_bid_card(b) for b in bids)
    return f"""
      <section class="company-card stripe-mid">
        <div class="company-head">
          <span class="company-name">나라장터 입찰공고</span>
          <span class="company-cat">공공 조달 · 자동 키워드 검색</span>
        </div>
        <div class="company-body">{cards}</div>
      </section>"""


def load_enrich(date: str) -> dict:
    """AI 다듬기 단계(예약 작업)가 만들어두는 선택적 보강 데이터. 없으면 빈 값으로 정상 동작."""
    path = ENRICH_DIR / f"{date}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def build_date_panel(data: dict, is_active: bool) -> str:
    date = data["date"]
    enrich = load_enrich(date)
    enrich_global = enrich.get("global", {})

    all_recent_titles = []
    for c in data["domestic"]:
        if isinstance(c["items"], list):
            all_recent_titles += [i["title"] for i in c["items"] if i.get("recent")]
    if isinstance(data.get("market", {}).get("items"), list):
        all_recent_titles += [i["title"] for i in data["market"]["items"] if i.get("recent")]
    keywords = enrich.get("keywords") or extract_keywords(all_recent_titles)
    if not keywords:
        fallback_titles = []
        for c in data["domestic"]:
            if isinstance(c["items"], list) and c["items"]:
                fallback_titles.append(c["items"][0]["title"])
        keywords = extract_keywords(fallback_titles) or ["데이터 축적 중"]
    keyword_chips = "".join(f'<span class="chip">#{esc(k)}</span>' for k in keywords)

    own = data.get("own")
    own_html = render_own_section(own) if own else ""
    competitor_html = "".join(render_company_section(c) for c in data["domestic"])
    domestic_html = own_html + competitor_html
    if not domestic_html:
        names = ([own["name"]] if own else []) + [c["name"] for c in data["domestic"]]
        domestic_html = f'<div class="empty">이 날짜엔 국내 소식 없음 (모니터링 대상: {esc(", ".join(names))})</div>'
    market_card = render_company_section({**data["market"], "category": ""}) if data.get("market") else ""
    market_section = f'<h2 class="section-title">국내 시장 전반</h2>{market_card}' if market_card else ""

    global_html = "".join(render_global_section(g, enrich_global) for g in data["global"]) or '<div class="empty">최근 24시간 내 해외 동향 없음</div>'

    bids_html = render_bids_section(load_bids(date))

    active_cls = " active" if is_active else ""
    return f"""
    <div class="date-panel{active_cls}" id="date-panel-{date}" data-date="{date}">
      <div class="chips">{keyword_chips}</div>
      <div class="domestic-content">
        {domestic_html}
        {market_section}
      </div>
      <div class="global-content">{global_html}</div>
      <div class="bids-content">{bids_html}</div>
    </div>"""


def main():
    files = sorted(RAW_DIR.glob("*.json"), reverse=True)[:MAX_DAYS]
    if not files:
        print("data/raw 에 파일이 없습니다. collect.py 를 먼저 실행하세요.")
        return

    datasets = [json.loads(f.read_text(encoding="utf-8")) for f in files]  # 최신순
    latest = datasets[0]

    date_tabs_html = "".join(
        f'<button class="date-tab{" active" if i == 0 else ""}" data-date="{d["date"]}">{d["date"]}</button>'
        for i, d in enumerate(datasets)
    )

    date_panels_html = "".join(build_date_panel(d, is_active=(i == 0)) for i, d in enumerate(datasets))

    archive_rows = ""
    for d in datasets:
        total = 0
        for c in d["domestic"]:
            if isinstance(c["items"], list):
                total += sum(1 for i in c["items"] if i.get("recent"))
        archive_rows += f'<tr class="archive-row" data-date="{d["date"]}"><td>{d["date"]}</td><td>{total}건</td><td>수집 완료</td></tr>'

    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>InfraEye·BigEye 경쟁사 레이더</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #f5f6f8; --card-bg: #ffffff; --text: #1a1d23; --text-dim: #6b7280;
    --border: #e5e7eb; --accent: #2563eb;
    --high: #dc2626; --mid: #d97706; --low: #16a34a;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: -apple-system, "Segoe UI", "Malgun Gothic", sans-serif; background: var(--bg); color: var(--text); }}
  header {{ background:#fff; border-bottom:1px solid var(--border); padding:20px 32px; display:flex; justify-content:space-between; align-items:center; }}
  header h1 {{ font-size:20px; margin:0; }}
  header .updated {{ color: var(--text-dim); font-size:13px; }}
  main {{ max-width: 1040px; margin: 0 auto; padding: 24px 20px 60px; }}
  .chips {{ margin-bottom: 20px; }}
  .chip {{ display:inline-block; background:#eef2ff; color:#3730a3; border-radius:999px; padding:5px 12px; margin:0 6px 6px 0; font-size:13px; font-weight:600; }}
  .date-tabs {{ display:flex; gap:8px; overflow-x:auto; padding-bottom:12px; margin-bottom: 20px; border-bottom:1px solid var(--border); }}
  .date-tab {{ border:1px solid var(--border); background:#fff; border-radius:8px; padding:8px 14px; font-size:13px; cursor:pointer; white-space:nowrap; color: var(--text-dim); }}
  .date-tab.active {{ background: var(--accent); color:#fff; border-color: var(--accent); font-weight:600; }}
  .subtabs {{ display:flex; gap:8px; margin-bottom:18px; }}
  .subtab {{ padding:8px 16px; border-radius:8px; font-size:14px; font-weight:600; cursor:pointer; color: var(--text-dim); }}
  .subtab.active {{ background:#fff; color:var(--text); box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .date-panel {{ display:none; }}
  .date-panel.active {{ display:block; }}
  body.mode-domestic .global-content, body.mode-domestic .bids-content {{ display:none; }}
  body.mode-global .domestic-content, body.mode-global .bids-content {{ display:none; }}
  body.mode-bids .domestic-content, body.mode-bids .global-content {{ display:none; }}
  .company-card {{ background: var(--card-bg); border-radius:10px; margin-bottom:14px; border:1px solid var(--border); border-left:4px solid #ccc; overflow:hidden; }}
  .stripe-high {{ border-left-color: var(--high); }}
  .stripe-mid {{ border-left-color: var(--mid); }}
  .stripe-low {{ border-left-color: var(--low); }}
  .company-head {{ display:flex; align-items:center; gap:10px; padding:14px 16px; border-bottom:1px solid var(--border); }}
  .company-name {{ font-weight:700; font-size:15px; }}
  .company-cat {{ color: var(--text-dim); font-size:12px; }}
  .badge-pill {{ margin-left:auto; font-size:11px; font-weight:700; padding:3px 10px; border-radius:999px; color:#fff; }}
  .badge-pill.badge-high {{ background: var(--high); }}
  .badge-pill.badge-mid {{ background: var(--mid); }}
  .badge-pill.badge-low {{ background: var(--low); }}
  .badge-pill.badge-own {{ background: var(--accent); }}
  .stripe-own {{ border-left-color: var(--accent); }}
  .company-body {{ padding: 6px 8px; }}
  .item-card {{ display:block; padding:10px 10px; border-radius:6px; text-decoration:none; color:inherit; }}
  .item-card:hover {{ background:#f8f9fb; }}
  .item-title {{ font-size:14px; font-weight:600; margin-bottom:3px; }}
  .item-title-orig {{ font-size:11px; color: var(--text-dim); margin-bottom:3px; }}
  .item-meta {{ font-size:12px; color: var(--text-dim); }}
  .empty {{ padding:14px 12px; font-size:13px; color: var(--text-dim); }}
  .why-line {{ padding: 4px 12px 12px; font-size:12px; color:#7c3aed; font-style:italic; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:10px; overflow:hidden; }}
  th, td {{ text-align:left; padding:10px 14px; border-bottom:1px solid var(--border); font-size:13px; }}
  th {{ color: var(--text-dim); font-weight:600; background:#fafafa; }}
  tr.archive-row {{ cursor:pointer; }}
  tr.archive-row:hover td {{ background:#f8f9fb; }}
  h2.section-title {{ font-size:16px; margin: 28px 0 12px; }}
</style>
</head>
<body class="mode-domestic">
<header>
  <h1>InfraEye·BigEye 경쟁사 레이더</h1>
  <div class="updated">마지막 갱신: {latest['date']} (KST 09:00 기준)</div>
</header>
<main>
  <div class="date-tabs">{date_tabs_html}</div>

  <div class="subtabs">
    <div class="subtab active" data-panel="domestic">국내</div>
    <div class="subtab" data-panel="global">해외</div>
    <div class="subtab" data-panel="bids">입찰정보</div>
  </div>

  {date_panels_html}

  <h2 class="section-title">최근 {MAX_DAYS}일 아카이브</h2>
  <table>
    <thead><tr><th>날짜</th><th>최근 소식 건수</th><th>상태</th></tr></thead>
    <tbody>{archive_rows}</tbody>
  </table>
</main>
<script>
  document.querySelectorAll('.subtab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      document.querySelectorAll('.subtab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      document.body.className = 'mode-' + tab.dataset.panel;
    }});
  }});

  function goToDate(date) {{
    document.querySelectorAll('.date-tab').forEach(t => t.classList.toggle('active', t.dataset.date === date));
    document.querySelectorAll('.date-panel').forEach(p => p.classList.toggle('active', p.dataset.date === date));
  }}
  document.querySelectorAll('.date-tab').forEach(tab => {{
    tab.addEventListener('click', () => goToDate(tab.dataset.date));
  }});
  document.querySelectorAll('.archive-row').forEach(row => {{
    row.addEventListener('click', () => {{
      goToDate(row.dataset.date);
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }});
  }});
</script>
</body>
</html>"""

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out = SITE_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"[렌더 완료] {out} ({len(datasets)}일치 포함)")


if __name__ == "__main__":
    main()
