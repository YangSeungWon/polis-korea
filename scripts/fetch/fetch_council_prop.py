"""data.go.kr 당선인 정보 API → 기초의원 비례(tc=9) 의석 '확정' 회수 (5~8회).

calc_proportional.py의 헤어식 추정이 모든 회차에서 비례 의석을 과소집계함
(5회 -12, 6회 -7, 7회 -5, 8회 -5). NEC 확정 비례 당선인 명부(sgTypecode=9)로 교체:
시군구·정당 매칭으로 candidates[].seats를 실제값으로 set + 누락 시군구 추가.

9회는 OpenAPI 미게시 → fetch_council_winners_live.py(라이브 포털 EPEI01) 사용.

사용:
  NEC_API_KEY=... .venv/bin/python scripts/fetch/fetch_council_prop.py --n 8
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://apis.data.go.kr/9760000/WinnerInfoInqireService2/getWinnerInfoInqire"
SGID = {5: "20100602", 6: "20140604", 7: "20180613", 8: "20220601"}
ORD = {5: "5th", 6: "6th", 7: "7th", 8: "8th"}
YEAR = {5: 2010, 6: 2014, 7: 2018, 8: 2022}

_SIDO_CANON = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"}
# 통합시 일반구(수원시팔달구 등) → 모도시(수원시). 비례는 시 단위라 일반구를 시로 묶음.
_PARENT_GU = re.compile(r"^([가-힣]+시)[가-힣]+구$")
# 시도 이동 — 데이터(현행) sido로 명부(당시) sido 매칭. 군위 2023 경북→대구.
_SIDO_HISTORY = {"군위군": ["경상북도", "대구광역시"]}


def norm(s: str) -> str:
    return (s or "").replace(" ", "").strip()


def canon_sido(s: str) -> str:
    return _SIDO_CANON.get(norm(s), norm(s))


def parent_city(sg: str) -> str:
    m = _PARENT_GU.match(sg)
    return m.group(1) if m else sg


def fetch_prop(key: str, sg_id: str):
    """sgTypecode=9 비례 당선인 → {(canon sido, norm 시군구): {정당: 의석}}."""
    by_sgg: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    page, total = 1, 0
    while True:
        url = (f"{API}?serviceKey={key}&sgId={sg_id}&sgTypecode=9"
               f"&pageNo={page}&numOfRows=100")
        root = ET.fromstring(urllib.request.urlopen(url, timeout=40).read())
        if root.findtext("header/resultCode") != "INFO-00":
            break
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            sido = canon_sido(it.findtext("sdName") or "")
            sgg = parent_city(norm(it.findtext("wiwName") or it.findtext("sggName") or ""))
            party = (it.findtext("jdName") or "무소속").strip()
            if sido and sgg:
                by_sgg[(sido, sgg)][party] += 1
        total = int(root.findtext("body/totalCount") or 0)
        if page * 100 >= total:
            break
        page += 1
    return by_sgg, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True, help="지선 회차 5/6/7/8")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = os.environ.get("NEC_API_KEY")
    if not key:
        print("ERR: NEC_API_KEY 필요", file=sys.stderr); sys.exit(1)
    n = args.n
    prop, total = fetch_prop(key, SGID[n])
    if not total:
        print(f"{n}회: OpenAPI 비례 당선인 없음(INFO-03). skip.", file=sys.stderr); return
    print(f"{n}회 비례 당선인 API: {total}석 · {len(prop)}개 시군구", file=sys.stderr)

    rp = ROOT / f"data/results/{ORD[n]}-local-{YEAR[n]}.sigungu.json"
    d = json.loads(rp.read_text(encoding="utf-8"))

    # 옛 추정 seats 전부 리셋 — 매칭 안 된 시군구가 옛 값을 유지해 합계 부풀리는 것 방지.
    for r in d.get("races", []):
        if r.get("sg_typecode") == "9":
            for c in (r.get("candidates") or []):
                c["seats"] = 0
                c["won"] = False

    def lookup(sido, sgg):
        m = prop.get((canon_sido(sido), parent_city(norm(sgg))))
        if m:
            return m, (canon_sido(sido), parent_city(norm(sgg)))
        for alt in _SIDO_HISTORY.get(norm(sgg), []):  # 시도 이동(군위 등)
            k = (canon_sido(alt), parent_city(norm(sgg)))
            if prop.get(k):
                return prop[k], k
        return None, None

    seen, marked = set(), 0
    by_party: dict[str, int] = defaultdict(int)
    for r in d.get("races", []):
        if r.get("sg_typecode") != "9":
            continue
        seats_map, mkey = lookup(r.get("sido"), r.get("sigungu") or "")
        if not seats_map:
            continue
        seen.add(mkey)
        for c in (r.get("candidates") or []):
            sv = seats_map.get(c.get("party"), 0)
            c["seats"] = sv
            c["won"] = sv > 0
            if sv:
                marked += sv
                by_party[c.get("party")] += sv
        r["seats_total"] = sum(seats_map.values())

    # 개표에 없던 비례 시군구 → 확정 의석만 추가 (득표 미상 = votes_pending).
    added = 0
    ins = max((i for i, r in enumerate(d["races"]) if r.get("sg_typecode") == "9"), default=len(d["races"])) + 1
    new = []
    for (sido, sgg), seats_map in prop.items():
        if (sido, sgg) in seen:
            continue
        cands = [{"party": p, "seats": sv, "won": True} for p, sv in sorted(seats_map.items(), key=lambda x: -x[1])]
        new.append({"sg_typecode": "9", "sido": sido, "sigungu": sgg, "scope": "proportional_sigungu",
                    "seats_total": sum(seats_map.values()), "votes_pending": True, "candidates": cands})
        added += 1
        for p, sv in seats_map.items():
            by_party[p] += sv; marked += sv
    d["races"][ins:ins] = new

    print(f"  확정 의석 {marked}/{total} ({marked / total:.1%}) · 매칭 시군구 {len(seen)} · 추가 {added}", file=sys.stderr)
    for p, c in sorted(by_party.items(), key=lambda x: -x[1]):
        print(f"    {p}: {c}", file=sys.stderr)
    if args.dry_run:
        print("  (dry-run)", file=sys.stderr); return
    if marked != total:
        print(f"  ⚠ {marked}≠{total} — 미저장.", file=sys.stderr); return
    rp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  → 저장 {rp.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
