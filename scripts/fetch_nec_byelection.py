"""NEC 재·보궐선거 실시사유 확정상황 API → data/raw/nec_byelection_2026.json.

API: https://apis.data.go.kr/9760000/RpbeExctRsnInqireService/getRpbeExctRsnCfmtnInfoInqire
인증키: .env의 NEC_API_KEY (NESDC와 동일 키)

NESDC region이 갑/을 미명기 짧게 등록된 경우(18000 '경기도 평택시'가 실제로
평택시을) NEC API 정확 선거구 정보로 보강하는 보조 source.
build_byelection가 가져다 쓰면 canon_district의 PDF 파일명 휴리스틱이
실패하는 케이스도 정확히 분류.

API 활성화 후 호출 가능. 활성화 안 됐으면 'API not found' 응답 → 캐시 유지.
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/raw/nec_byelection_2026.json"

API_BASE = "https://apis.data.go.kr/9760000/RpbeExctRsnInqireService"
ENDPOINT = "/getRpbeExctRsnCfmtnInfoInqire"
SG_VOTEDATE = "20260603"  # 9회 지선·재보궐 같은 날


def fetch(api_key: str, page: int = 1, num: int = 100) -> dict:
    params = {
        "serviceKey": api_key,
        "pageNo": str(page),
        "numOfRows": str(num),
        "sgVotedate": SG_VOTEDATE,
        "_type": "json",
    }
    url = f"{API_BASE}{ENDPOINT}?{urllib.parse.urlencode(params, safe='%')}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e)}
    if raw.strip().startswith("<"):
        return {"error": "XML response (likely error page)", "raw": raw[:400]}
    if raw.startswith("API not"):
        return {"error": raw.strip()}
    try:
        return json.loads(raw)
    except Exception:
        return {"error": "JSON parse fail", "raw": raw[:400]}


def main():
    api_key = os.environ.get("NEC_API_KEY")
    if not api_key:
        # .env에서 load
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("NEC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not api_key:
        print("ERROR: NEC_API_KEY 미설정 (.env)", file=sys.stderr)
        sys.exit(1)

    all_rows: list[dict] = []
    page = 1
    while True:
        r = fetch(api_key, page=page, num=100)
        if "error" in r:
            print(f"  page {page}: {r['error']}", file=sys.stderr)
            if not all_rows:
                print(f"API 호출 실패 (활성화 대기 중일 가능성): {r.get('error')}",
                      file=sys.stderr)
                sys.exit(2)
            break
        # 응답 구조 추정: response.body.items.item[] 또는 비슷
        body = r.get("response", {}).get("body", {})
        items = body.get("items", [])
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, list):
            all_rows.extend(items)
        total_count = int(body.get("totalCount", 0) or 0)
        if len(all_rows) >= total_count or not items:
            break
        page += 1
        time.sleep(0.3)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"NEC 재보궐: {len(all_rows)} rows → {OUT.relative_to(ROOT)}", file=sys.stderr)
    # 시도별·선거구별 요약
    by_sido: dict[str, list[str]] = {}
    for row in all_rows:
        sido = row.get("sdName", row.get("sido", "?"))
        sgg = row.get("sggName", row.get("sgg", "?"))
        by_sido.setdefault(sido, []).append(sgg)
    for sido, ggs in sorted(by_sido.items()):
        print(f"  {sido}: {', '.join(sorted(set(ggs)))}", file=sys.stderr)


if __name__ == "__main__":
    main()
