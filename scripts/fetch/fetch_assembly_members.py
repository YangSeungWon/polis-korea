"""현직 국회의원 → data/assembly/current.json ('지금 의석').

출처: 열린국회정보(open.assembly.go.kr) Open API — 국회의원 정보 통합 API
(nwvrqwxyaytdsfvhu). 현 대수 재적 의원만 준다.

왜 이것이 정본인가: 총선 뒤 의석은 재·보궐만으로 바뀌지 않는다. 탈당·입당·합당,
비례 승계, 위성정당 복귀가 훨씬 크다. 재보궐 사유(byelection_reasons)로 총선 결과를
고쳐 '지금'을 만들면 일부만 고친 숫자가 '현재'라는 이름을 단다 — 그래서 의원 명부를
그대로 센다.

남기는 것: 이름·정당·지역구/비례·선거구·선수. 연락처·보좌진·약력은 받지 않는다
(화면에 안 쓰는 개인 정보를 저장소에 쌓지 않는다).

공석 = 정원 - 재적. 정원은 공직선거법 제21조(지역구 254 + 비례 46 = 300, 22대).
'모른다'가 아니라 '비어 있다'다 — 사유는 byelection_reasons의 upcoming에 있다.

인증키: 환경변수 ASSEMBLY_API_KEY, 없으면 .env. 키 없이 부르면 API가 5줄 샘플만
주므로, 재적 수와 받은 줄 수가 다르면 쓰지 않고 죽는다(반쪽 명부를 '지금'으로 내지 않는다).

사용: .venv/bin/python scripts/fetch/fetch_assembly_members.py
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "assembly" / "current.json"
API = "https://open.assembly.go.kr/portal/openapi/nwvrqwxyaytdsfvhu"
SEATS_BY_LAW = 300   # 공직선거법 제21조 — 바뀌면 여기와 검사가 함께 바뀐다
PAGE = 100


def api_key() -> str | None:
    k = os.environ.get("ASSEMBLY_API_KEY")
    if k:
        return k.strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ASSEMBLY_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def get(page: int, key: str) -> tuple[int, list[dict]]:
    qs = urllib.parse.urlencode({"KEY": key, "Type": "json", "pIndex": page, "pSize": PAGE})
    # UA가 없으면 'Bad Request.'를 돌려준다.
    req = urllib.request.Request(f"{API}?{qs}", headers={"User-Agent": "Mozilla/5.0 (polis data fetch)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    if "RESULT" in d:
        raise SystemExit(f"✗ API 오류: {d['RESULT']}")
    head, body = d["nwvrqwxyaytdsfvhu"]
    res = head["head"][1]["RESULT"]
    if res.get("CODE") != "INFO-000":
        raise SystemExit(f"✗ API 오류: {res}")
    return head["head"][0]["list_total_count"], body.get("row", [])


def main() -> int:
    key = api_key()
    if not key:
        print("✗ ASSEMBLY_API_KEY가 없다 (.env 또는 환경변수)", file=sys.stderr)
        return 1
    total, rows, page = None, [], 1
    while True:
        t, rs = get(page, key)
        total = t if total is None else total
        rows += rs
        if len(rows) >= total or not rs:
            break
        page += 1
    if len(rows) != total:
        print(f"✗ 재적 {total}명인데 {len(rows)}명만 받았다 — 쓰지 않는다", file=sys.stderr)
        return 1

    members = sorted(({
        "name": r["HG_NM"],
        "party": (r.get("POLY_NM") or "").strip() or None,
        "kind": r.get("ELECT_GBN_NM"),            # 지역구 | 비례대표
        "district": r.get("ORIG_NM"),             # 비례면 '비례대표'
        "reelected": r.get("REELE_GBN_NM"),
        "code": r.get("MONA_CD"),
    } for r in rows), key=lambda m: (m["party"] or "", m["kind"] or "", m["district"] or "", m["name"]))
    unknown = [m["name"] for m in members if not m["party"]]
    if unknown:
        print(f"✗ 정당을 모르는 의원 {unknown[:5]} — 쓰지 않는다", file=sys.stderr)
        return 1
    # UNITS는 의원의 역대 대수 목록("제20대, 제22대")이다 — 가장 큰 대수가 지금 국회.
    units = sorted({int(n) for r in rows for n in re.findall(r"제(\d+)대", r.get("UNITS") or "")})
    cnt = collections.Counter(m["party"] for m in members)
    seats = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
    out = {
        "_meta": {
            "source": "열린국회정보 Open API · 국회의원 정보 통합 API (nwvrqwxyaytdsfvhu)",
            "url": "https://open.assembly.go.kr/",
            "fetched": date.today().isoformat(),
            "assembly": f"제{units[-1]}대" if units else None,
            "seats_by_law": SEATS_BY_LAW,
            "note": "재적 의원의 지금 소속 정당. 총선 당일 결과가 아니다 — 탈당·입당·합당·"
                    "비례 승계가 반영된다. 공석 = 정원 - 재적.",
        },
        "seated": len(members),
        "vacant": SEATS_BY_LAW - len(members),
        "party_seats": [[p, n] for p, n in seats],
        "members": members,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}: 재적 {len(members)} · 공석 {out['vacant']} · "
          + " · ".join(f"{p} {n}" for p, n in seats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
