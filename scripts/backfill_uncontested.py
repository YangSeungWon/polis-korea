"""무투표 당선 선거구 백필 — 개표 기반 소스(WWolf 등)에 빠진 무투표 당선구를
NEC 무투표선거구 API로 가져와 centroid + results 양쪽에 자동 병합.

무투표 당선(단독 출마)은 개표가 없어 득표 기반 데이터셋엔 행이 없다.
예) 20대 경남 통영시고성군 — 이군현(새누리당), 1988년 이후 첫 무투표.

흐름:
  1. 캐시(data/raw/nec_uncontested/{n}.json) 있으면 사용.
  2. 없고 NEC_API_KEY 있으면 API 호출 후 캐시 저장 (공개 데이터 — 커밋 가능).
  3. 캐시를 district_{n}_centroid.json + results/national_assembly_{n}.json 에 병합.
     - 이미 있으면 skip (멱등).

API: WtvtelpcInfoInqireService (data.go.kr 9760000), sgTypecode=2(국회의원).

사용:
  .venv/bin/python scripts/backfill_uncontested.py 20            # 캐시/results/centroid 병합
  NEC_API_KEY=... .venv/bin/python scripts/backfill_uncontested.py 20  # 캐시 새로 받기
  .venv/bin/python scripts/backfill_uncontested.py 17,18,19,20,21,22   # 여러 회차
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "raw" / "nec_uncontested"
API_URL = "https://apis.data.go.kr/9760000/WtvtelpcInfoInqireService/getWtvtelpcsccnInfoInqire"

# 선거ID = 선거일 YYYYMMDD (fetch_districts_api와 동일)
ELECTION_DATES = {
    17: "20040415", 18: "20080409", 19: "20120411",
    20: "20160413", 21: "20200415", 22: "20240410",
}


def fetch_uncontested(key: str, sg_id: str, sg_typecode: int = 2) -> list[dict]:
    """무투표 당선 선거구 list. sgTypecode=2 국회의원."""
    url = (f"{API_URL}?serviceKey={key}&sgId={sg_id}&sgTypecode={sg_typecode}"
           f"&pageNo=1&numOfRows=100")
    root = ET.fromstring(urllib.request.urlopen(url, timeout=30).read())
    if root.findtext("header/resultCode") != "INFO-00":
        print(f"  ! API {root.findtext('header/resultMsg')}", file=sys.stderr)
        return []
    out = []
    for it in root.findall("body/items/item"):
        out.append({
            "sido": it.findtext("sdName") or "",
            "name": it.findtext("sggName") or "",
            "winner": it.findtext("name") or "",
            "winner_party": it.findtext("jdName") or "",
        })
    return out


def load_uncontested(n: int) -> list[dict]:
    """캐시 우선, 없으면 API(키 필요) 호출 후 캐시 저장."""
    cache = CACHE_DIR / f"{n}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    key = os.environ.get("NEC_API_KEY")
    if not key:
        print(f"  {n}대: 캐시 없음 + NEC_API_KEY 없음 → skip", file=sys.stderr)
        return []
    sg_id = ELECTION_DATES.get(n)
    if not sg_id:
        return []
    rows = fetch_uncontested(key, sg_id)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {n}대: API → 캐시 저장 ({len(rows)}건) {cache.relative_to(ROOT)}", file=sys.stderr)
    return rows


def backfill(n: int) -> None:
    rows = load_uncontested(n)
    if not rows:
        print(f"{n}대: 무투표 선거구 없음")
        return

    # 1. centroid 병합 (sido+name만 — 위치는 build_district_hex_v2가 시군구 geo로 계산)
    cp = ROOT / f"data/geo/district_{n}_centroid.json"
    centroid = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else []
    have_c = {(d["sido"], d["name"]) for d in centroid}
    added_c = 0
    for u in rows:
        if (u["sido"], u["name"]) not in have_c:
            centroid.append({"sido": u["sido"], "name": u["name"]})
            added_c += 1
    if added_c:
        cp.write_text(json.dumps(centroid, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. results district[] 병합 (uncontested:true, 득표 null)
    rp = ROOT / f"data/results/national_assembly_{n}.json"
    res = json.loads(rp.read_text(encoding="utf-8"))
    res.setdefault("district", [])
    have_r = {(d["sido"], d["name"]) for d in res["district"]}
    added_r = 0
    for u in rows:
        if (u["sido"], u["name"]) in have_r:
            continue
        res["district"].append({
            "sido": u["sido"], "name": u["name"],
            "winner": u["winner"], "winner_party": u["winner_party"],
            "uncontested": True,
            "candidates": [{"name": u["winner"], "party": u["winner_party"],
                            "votes": None, "pct": None}],
        })
        added_r += 1
    if added_r:
        rp.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    names = ", ".join(f"{u['name']}({u['winner']}·{u['winner_party']})" for u in rows)
    print(f"{n}대 무투표 {len(rows)}건: {names} | centroid +{added_c}, results +{added_r}")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "20"
    for n in [int(x) for x in arg.split(",")]:
        backfill(n)


if __name__ == "__main__":
    main()
