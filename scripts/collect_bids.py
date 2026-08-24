"""
경쟁사 레이더 - 나라장터(공공입찰) 수집
조달청 나라장터 입찰공고정보서비스 Open API (data.go.kr) 사용.
AI 미사용, 패턴(공식 API 조회) 기반. 우리 사업 영역 키워드로 최근 입찰공고를 조회한다.

사전 준비: data.go.kr 에서 "조달청_나라장터 입찰공고정보서비스" 활용신청 후
발급받은 일반 인증키(Decoding)를 환경변수 G2B_SERVICE_KEY 로 설정하거나
scripts/g2b_key.txt 파일에 한 줄로 저장해둘 것 (git에는 커밋하지 않음).
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "bids"
KEY_FILE = ROOT / "scripts" / "g2b_key.txt"

KST = timezone(timedelta(hours=9))
LOOKBACK_HOURS = 48

BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"

# 업무구분별 오퍼레이션 (물품/용역 키워드 검색)
OPERATIONS = {
    "용역": "getBidPblancListInfoServcPPSSrch",
    "물품": "getBidPblancListInfoThngPPSSrch",
}

# 우리 사업 영역 키워드 (공고명에 포함되는지로 검색)
KEYWORDS = ["통합관제", "네트워크관리시스템", "NMS", "로그관리", "SIEM", "옵저버빌리티", "보안관제"]


def load_service_key() -> str:
    key = os.environ.get("G2B_SERVICE_KEY")
    if key:
        return key.strip()
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        f"서비스키를 찾을 수 없습니다. 환경변수 G2B_SERVICE_KEY 를 설정하거나 {KEY_FILE} 파일에 키를 저장하세요."
    )


def fetch_bids(operation: str, keyword: str, begin_dt: str, end_dt: str, service_key: str) -> list:
    # data.go.kr의 "일반 인증키"는 이미 URL 인코딩된 값이라 urlencode()로 다시 감싸면 이중 인코딩되어 인증 실패한다.
    # serviceKey는 원문 그대로 URL에 붙이고, 나머지 파라미터만 urlencode한다.
    other_params = {
        "numOfRows": "50",
        "pageNo": "1",
        "inqryDiv": "1",
        "inqryBgnDt": begin_dt,
        "inqryEndDt": end_dt,
        "bidNtceNm": keyword,
        "type": "json",
    }
    url = f"{BASE_URL}/{operation}?serviceKey={service_key}&{urllib.parse.urlencode(other_params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [{"_error": "JSON 파싱 실패 (응답이 XML/에러 페이지일 수 있음)", "_raw_head": raw[:300]}]

    body = data.get("response", {}).get("body", {})
    items = body.get("items", "")
    if items == "" or items is None:
        return []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items


def main():
    try:
        service_key = load_service_key()
    except RuntimeError as e:
        print(f"[중단] {e}", file=sys.stderr)
        sys.exit(1)

    now_kst = datetime.now(KST)
    begin_dt = (now_kst - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y%m%d0000")
    end_dt = now_kst.strftime("%Y%m%d2359")
    today_str = now_kst.strftime("%Y-%m-%d")

    print(f"[나라장터 수집 시작] {today_str} (최근 {LOOKBACK_HOURS}시간, {begin_dt}~{end_dt})", file=sys.stderr)

    result = {"date": today_str, "collected_at": datetime.now(timezone.utc).isoformat(), "bids": []}

    seen_notice_no = set()
    for biz_type, operation in OPERATIONS.items():
        for kw in KEYWORDS:
            items = fetch_bids(operation, kw, begin_dt, end_dt, service_key)
            if items and isinstance(items[0], dict) and "_error" in items[0]:
                print(f"  - [{biz_type}] '{kw}': 오류 - {items[0]['_error']}", file=sys.stderr)
                continue
            new_count = 0
            for it in items:
                notice_no = it.get("bidNtceNo", "")
                if notice_no and notice_no in seen_notice_no:
                    continue
                seen_notice_no.add(notice_no)
                result["bids"].append({
                    "biz_type": biz_type,
                    "matched_keyword": kw,
                    "title": it.get("bidNtceNm", ""),
                    "notice_no": notice_no,
                    "org": it.get("dminsttNm", ""),
                    "close_date": it.get("bidClseDt", ""),
                    "link": it.get("bidNtceDtlUrl", "") or it.get("bidNtceUrl", ""),
                })
                new_count += 1
            print(f"  - [{biz_type}] '{kw}': {new_count}건", file=sys.stderr)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{today_str}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[저장 완료] {out_path} (총 {len(result['bids'])}건)", file=sys.stderr)


if __name__ == "__main__":
    main()
