"""
경쟁사 레이더 - 1단계: 패턴 기반 데이터 수집 (RSS)
AI 미사용. Google 뉴스 RSS만으로 회사명/키워드 검색 결과를 그대로 가져와
data/raw/<오늘날짜>.json 에 저장한다. 다음 단계(분류/다듬기)의 입력이 된다.
"""

import json
import re
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "raw"

KST = timezone(timedelta(hours=9))
RECENCY_HOURS = 48  # 브리프 기준: 최근 24~48시간

# 국내 경쟁사 5곳
DOMESTIC_COMPANIES = [
    {"id": "brains", "name": "브레인즈컴퍼니", "query": "브레인즈컴퍼니 제니우스", "category": "NMS·통합관제"},
    {"id": "logpresso", "name": "로그프레소", "query": "로그프레소 Logpresso", "category": "로그관리·SIEM"},
    {"id": "piolink", "name": "파이오링크", "query": "파이오링크 PIOLINK", "category": "보안·네트워크 인접"},
    {"id": "whatap", "name": "와탭랩스", "query": "와탭랩스 WhaTap", "category": "APM·옵저버빌리티"},
    {"id": "igloo", "name": "이글루코퍼레이션", "query": "이글루코퍼레이션", "category": "보안관제·SIEM"},
]

# 자사 (정합성 확인용 — 이미 아는 사실과 비교해서 수집 결과를 신뢰할 수 있는지 체크)
OWN_COMPANY = {"id": "own", "name": "티사이언티픽", "query": "티사이언티픽", "category": "자사"}

# 국내 시장 전반
MARKET_QUERY = {"id": "market", "name": "국내 시장 전반", "query": "NMS 통합관제 로그관리 SIEM 시장"}

# 해외 동향 (옵저버빌리티 주요 벤더)
GLOBAL_QUERIES = [
    {"id": "datadog", "name": "Datadog"},
    {"id": "dynatrace", "name": "Dynatrace"},
    {"id": "splunk", "name": "Splunk"},
    {"id": "elastic", "name": "Elastic Observability"},
    {"id": "newrelic", "name": "New Relic"},
    {"id": "manageengine", "name": "ManageEngine"},
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def fetch_rss(query: str, lang="ko", country="KR", ceid="KR:ko") -> str:
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={country}&ceid={ceid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_pubdate(raw: str):
    # RFC 822 형식: "Tue, 13 Jan 2026 08:00:00 GMT"
    try:
        dt = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def clean_title(title: str) -> str:
    # Google 뉴스는 보통 "제목 - 매체명" 형태. 뒤쪽 매체명은 <source>가 따로 있으니 제거.
    return re.sub(r"\s+-\s+[^-]{1,30}$", "", title).strip()


def parse_items(xml_text: str, since: datetime):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("./channel/item"):
        title_raw = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""

        pub_dt = parse_pubdate(pub_raw)
        if pub_dt is None:
            continue

        items.append({
            "title": clean_title(title_raw),
            "link": link,
            "source": source,
            "pubDate": pub_dt.isoformat(),
            "recent": pub_dt >= since,
        })

    # 최신순 정렬 + 제목 중복 제거
    items.sort(key=lambda x: x["pubDate"], reverse=True)
    seen = set()
    deduped = []
    for it in items:
        key = it["title"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped


def collect_one(query: str, lang="ko", country="KR", ceid="KR:ko", since=None):
    try:
        xml_text = fetch_rss(query, lang, country, ceid)
        return parse_items(xml_text, since)
    except Exception as e:
        return {"error": str(e)}


def main():
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(hours=RECENCY_HOURS)
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")

    result = {
        "date": today_kst,
        "collected_at": now_utc.isoformat(),
        "recency_hours": RECENCY_HOURS,
        "domestic": [],
        "own": None,
        "market": None,
        "global": [],
    }

    print(f"[수집 시작] {today_kst} (최근 {RECENCY_HOURS}시간 기준)", file=sys.stderr)

    for c in DOMESTIC_COMPANIES:
        items = collect_one(c["query"], since=since)
        n_recent = sum(1 for i in items if i.get("recent")) if isinstance(items, list) else 0
        print(f"  - {c['name']}: 전체 {len(items) if isinstance(items, list) else 'ERR'}건, 최근 {n_recent}건", file=sys.stderr)
        result["domestic"].append({**c, "items": items})

    own_items = collect_one(OWN_COMPANY["query"], since=since)
    n_recent = sum(1 for i in own_items if i.get("recent")) if isinstance(own_items, list) else 0
    print(f"  - [자사] {OWN_COMPANY['name']}: 전체 {len(own_items) if isinstance(own_items, list) else 'ERR'}건, 최근 {n_recent}건", file=sys.stderr)
    result["own"] = {**OWN_COMPANY, "items": own_items}

    market_items = collect_one(MARKET_QUERY["query"], since=since)
    n_recent = sum(1 for i in market_items if i.get("recent")) if isinstance(market_items, list) else 0
    print(f"  - [시장전반]: 전체 {len(market_items) if isinstance(market_items, list) else 'ERR'}건, 최근 {n_recent}건", file=sys.stderr)
    result["market"] = {**MARKET_QUERY, "items": market_items}

    for g in GLOBAL_QUERIES:
        items = collect_one(g["name"], lang="en-US", country="US", ceid="US:en", since=since)
        n_recent = sum(1 for i in items if i.get("recent")) if isinstance(items, list) else 0
        print(f"  - [해외] {g['name']}: 전체 {len(items) if isinstance(items, list) else 'ERR'}건, 최근 {n_recent}건", file=sys.stderr)
        result["global"].append({**g, "items": items})

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{today_kst}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[저장 완료] {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
