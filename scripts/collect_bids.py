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
# InfraEye(NMS/EMS)·BigEye(로그관리/SIEM) 제품 자료(1.지식스토리지) 기준으로 정밀화.
# "통합관제시스템"처럼 "시스템" 접미사를 붙여 좁히면 "스마트도시 통합관제플랫폼 구축",
# "OO 보안관제 운영 용역"처럼 실제로 관련 있는 정상 공고까지 놓치는 것을 실제 API 호출로 확인했음.
# 그래서 기존 뭉뚱그린 키워드는 그대로 유지해 재현율을 지키고, 대신 아래 EXCLUDE_KEYWORDS로
# 지명·시설명 등과 우연히 겹치는 IT 무관 공고만 걸러낸다.
# "인프라통합관리", "이상행위탐지"는 InfraEye/BigEye(PIS 모듈) 제품 자료에 근거해 새로 추가.
# "EMS"는 제외 — 실제 조회 결과 "EMS 보급지원사업"(에너지관리시스템, 우리 제품과 무관) 등에
# 걸리는 것을 확인해 채택하지 않음.
KEYWORDS = [
    "통합관제",
    "네트워크관리시스템",
    "NMS",
    "로그관리",
    "SIEM",
    "옵저버빌리티",
    "보안관제",
    "인프라통합관리",
    "이상행위탐지",
]

# 제외 키워드 (공고명에 하나라도 포함되면 결과에서 제외)
# 포함 키워드와 우연히 겹치는 공사/청소/시설관리/폐기물처리/차량 등 IT와 무관한 용역 필터링용.
# 예: "군자기지 통합관제센터 대체진입로 개설공사 건설폐기물 처리용역" 같은 오탐 제거.
EXCLUDE_KEYWORDS = [
    "공사", "철거", "신축", "증축", "리모델링", "포장", "조경", "진입로",
    "폐기물", "청소", "방역", "소독",
    "차량", "주차장",
    "경비", "미화",
]


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
            excluded_count = 0
            for it in items:
                notice_no = it.get("bidNtceNo", "")
                if notice_no and notice_no in seen_notice_no:
                    continue
                title = it.get("bidNtceNm", "")
                if any(ex_kw in title for ex_kw in EXCLUDE_KEYWORDS):
                    excluded_count += 1
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
            print(f"  - [{biz_type}] '{kw}': {new_count}건 (제외 {excluded_count}건)", file=sys.stderr)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{today_str}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[저장 완료] {out_path} (총 {len(result['bids'])}건)", file=sys.stderr)


if __name__ == "__main__":
    main()
