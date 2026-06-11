"""info.nec.go.kr 당선인 명부(EPEI01) → 광역의원·기초장 확정 (tc4·tc5·tc8).

라이브 개표(fetch_nec_live)는 무투표 선거구를 빼먹고, calc_proportional은 8회 baseline
정수를 써서 9회 비례를 과소집계한다:
- tc4 기초장 224→227, tc5 광역의원 686→804 (무투표 선거구 보충).
- tc8 광역비례 87→129 (9회 정수 증가분; calc 추정 대체).
확정 명부(EPEI01_#4/#5/#8)로 won·seats를 실값으로 교체. 전남광주통합 시도의회는
중선거구라 tc5는 시군구로 광주/전남 분리·다중당선, tc8은 통합 1 entity로 둠.

기초의원(tc6 중선거구·tc9 비례)은 fetch_council_winners_live.py 참고.

사용:
  .venv/bin/python scripts/fetch/fetch_single_winners_live.py            # 9회 tc4+tc5+tc8
  .venv/bin/python scripts/fetch/fetch_single_winners_live.py --dry-run
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://info.nec.go.kr"
SHOW = "/m/main/showDocument.xhtml"
REPORT = "/m/electioninfo/electionInfo_report.json"
CITYBOX = "/m/bizcommon/selectbox/selectbox_cityCodeBySgJson.json"

ELECTION_ID = {9: "0020260603"}
RESULTS = {9: "data/results/9th-local-2026.json"}

# tc → (electionCode, 우리 race의 선거구 필드). SGGNAME(명부 단위)로 매칭.
OFFICES = {
    "4": {"code": "4", "race_unit": "sigungu", "label": "기초단체장"},
    "5": {"code": "5", "race_unit": "district", "label": "광역의원 지역구"},
}
_SIDO_CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도"}
# 전남광주 통합 시도의회(tc5): 선거구가 모두 한 cityCode·SDNAME=전남광주통합특별시로 옴.
# 시군구(WIWNAME)로 광주(5 자치구)/전남 분리 — 우리 데이터(분리 sido)와 맞춤.
_GWANGJU_GU = {"동구", "서구", "남구", "북구", "광산구"}


def norm(s: str) -> str:
    return (s or "").replace(" ", "").strip()


def canon_sido(s: str) -> str:
    return _SIDO_CANON.get(norm(s), norm(s))


def to_int(s) -> int:
    try:
        return int(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def make_session(eid: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    s.get(f"{BASE}{SHOW}", params={"electionId": eid, "topMenuId": "EP", "secondMenuId": "EPEI01"}, timeout=20)
    return s


def fetch_winners(s: requests.Session, eid: str, code: str):
    """EPEI01_#code 시도별 → {(canon sido, norm SGGNAME): [winner dict, ...]}.
    보통 단위당 1명이나, 전남광주통합특별시 광역의원은 중선거구(2~4명)라 리스트."""
    rc = s.get(f"{BASE}{CITYBOX}", params={"electionId": eid, "electionCode": code}, timeout=20)
    cities = rc.json().get("jsonResult", {}).get("body") or []
    out: dict[tuple, list] = defaultdict(list)
    total = 0
    for c in cities:
        # 시도는 cityCode의 NAME 사용 — 전남광주 통합 시도의회라도 cityCode는 광주/전남
        # 분리(2900/4600)이고 row SDNAME만 '전남광주통합특별시'. 우리 데이터(분리)와 맞춤.
        city_sido = (c.get("NAME") or "").strip()
        data = {"electionId": eid, "secondMenuId": "EPEI01", "topMenuId": "EP",
                "statementId": f"EPEI01_#{code}", "electionCode": code,
                "cityCode": str(c.get("CODE")), "sggCityCode": "-1", "townCode": "-1"}
        r = s.post(f"{BASE}{REPORT}", data=data, timeout=30)
        for row in r.json().get("jsonResult", {}).get("body") or []:
            sdname = (row.get("SDNAME") or "").strip()
            wiw = norm(row.get("WIWNAME") or "")
            if "전남광주" in sdname or "통합" in sdname:   # 통합 의회 → 시군구로 광주/전남 분리
                sido = "광주광역시" if wiw in _GWANGJU_GU else "전라남도"
            else:
                sido = canon_sido(city_sido)
            unit = norm(row.get("SGGNAME", ""))
            nm = norm(row.get("K_NAME", ""))
            if not (sido and unit and nm):
                continue
            dugsu = (row.get("DUGSU") or "").strip()
            out[(sido, unit)].append({
                "name": nm, "party": (row.get("JDNAME") or "무소속").strip(),
                "votes": to_int(dugsu), "uncontested": "무투표" in dugsu,
                "sido": sido,
                "sigungu": (row.get("WIWNAME") or row.get("SGGNAME") or "").strip(),
                "district": (row.get("SGGNAME") or "").strip(),
            })
            total += 1
    return out, total


def fetch_prop8(s: requests.Session, eid: str):
    """EPEI01_#8 광역의원 비례 당선인 → {canon sido: {party: 의석}}. SGGNAME=시도(전남광주 통합).
    HUBOID로 중복제거(DI cityCode가 통합/분리 중복 반환)."""
    rc = s.get(f"{BASE}/m/bizcommon/selectbox/selectbox_cityCodeDIBySgJson.json",
               params={"electionId": eid, "electionCode": "8"}, timeout=20)
    cities = rc.json().get("jsonResult", {}).get("body") or []
    by_sido: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    seen = set()
    for c in cities:
        data = {"electionId": eid, "secondMenuId": "EPEI01", "topMenuId": "EP",
                "statementId": "EPEI01_#8", "electionCode": "8",
                "cityCode": str(c.get("CODE")), "sggCityCode": "-1", "townCode": "-1"}
        r = s.post(f"{BASE}{REPORT}", data=data, timeout=30)
        for row in r.json().get("jsonResult", {}).get("body") or []:
            hid = row.get("HUBOID")
            if hid in seen:
                continue
            seen.add(hid)
            sido = canon_sido(row.get("SGGNAME", ""))
            party = (row.get("JDNAME") or "무소속").strip()
            if sido:
                by_sido[sido][party] += 1
    return by_sido, len(seen)


def process_prop8(d: dict, by_sido: dict):
    """tc8 광역의원 비례 — 명부 의석으로 교체 (calc_proportional 추정 대체).
    9회 비례 정수 증가(87→129)를 calc이 8회 baseline으로 과소집계했음."""
    marked = 0
    by_party: dict[str, int] = defaultdict(int)
    for r in d.get("races", []):
        if r.get("sg_typecode") != "8":
            continue
        seats_map = by_sido.get(canon_sido(r.get("sido")))
        if not seats_map:
            continue
        for c in (r.get("candidates") or []):
            sv = seats_map.get(c.get("party"), 0)
            c["seats"] = sv
            c["won"] = sv > 0
            if sv:
                marked += sv
                by_party[c.get("party")] += sv
        r["seats_total"] = sum(seats_map.values())
    return marked, by_party


def process(d: dict, tc: str, race_unit: str, winners: dict):
    """tc 당선직: 명부로 won 확정 + 누락(무투표) race 추가. 단위당 1명(보통)~N명(통합 중선거구)."""
    seen, marked = set(), 0
    by_party: dict[str, int] = defaultdict(int)
    for r in d.get("races", []):
        if r.get("sg_typecode") != tc:
            continue
        key = (canon_sido(r.get("sido")), norm(r.get(race_unit) or ""))
        ws = winners.get(key)
        if not ws:
            continue
        seen.add(key)
        wnames = {w["name"] for w in ws}
        got = set()
        for c in (r.get("candidates") or []):
            won = norm(c.get("name")) in wnames
            c["won"] = won
            if won:
                got.add(norm(c.get("name")))
                marked += 1
                by_party[c.get("party") or "무소속"] += 1
        # 후보 명단에 없는 당선자(무투표·빈 명단) 보충.
        for w in ws:
            if w["name"] not in got:
                r.setdefault("candidates", []).append({
                    "name": w["name"], "party": w["party"], "votes": w["votes"],
                    "won": True, "is_uncontested": w["uncontested"]})
                marked += 1
                by_party[w["party"]] += 1
        if any(w["uncontested"] for w in ws):
            r["is_uncontested"] = True
        r["seats_total"] = len(ws)
    # 개표에 없던 단위 → 당선자(들)로 race 추가.
    added = 0
    ins = max((i for i, r in enumerate(d["races"]) if r.get("sg_typecode") == tc), default=len(d["races"])) + 1
    new = []
    for key, ws in winners.items():
        if key in seen:
            continue
        w0 = ws[0]
        cands = [{"name": w["name"], "party": w["party"], "votes": w["votes"],
                  "rank": i + 1, "won": True, "is_uncontested": w["uncontested"]} for i, w in enumerate(ws)]
        race = {"sg_typecode": tc, "sido": w0["sido"],
                "sigungu": w0["sigungu"], "scope": "sigungu" if tc == "4" else "district",
                "count_pct": 100.0, "is_uncontested": all(w["uncontested"] for w in ws),
                "seats_total": len(ws), "candidates": cands}
        if tc == "5":
            race["district"] = w0["district"]
        new.append(race)
        added += len(ws)
        for w in ws:
            by_party[w["party"]] += 1
            marked += 1
    d["races"][ins:ins] = new
    return marked, added, len(seen), by_party


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=9)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    eid = ELECTION_ID[args.n]
    rp = ROOT / RESULTS[args.n]
    d = json.loads(rp.read_text(encoding="utf-8"))
    s = make_session(eid)
    ok = True
    for tc, info in OFFICES.items():
        winners, total = fetch_winners(s, eid, info["code"])
        if not total:
            print(f"[tc{tc} {info['label']}] 명부 없음 — skip", file=sys.stderr); ok = False; continue
        marked, added, matched, by_party = process(d, tc, info["race_unit"], winners)
        print(f"[tc{tc} {info['label']}] 명부 {total} · 매칭 {matched} · 추가(무투표) {added} · 확정 {marked}/{total} ({marked/total:.1%})", file=sys.stderr)
        for p, c in sorted(by_party.items(), key=lambda x: -x[1])[:6]:
            print(f"    {p}: {c}", file=sys.stderr)
        if marked != total:
            ok = False
    # tc8 광역의원 비례 — 명부 의석(_#8)으로 교체
    p8, t8 = fetch_prop8(s, eid)
    m8, bp8 = process_prop8(d, p8)
    print(f"[tc8 광역의원 비례] 명부 {t8} · 확정 의석 {m8}/{t8} ({m8/t8:.1%})", file=sys.stderr)
    for p, c in sorted(bp8.items(), key=lambda x: -x[1])[:6]:
        print(f"    {p}: {c}", file=sys.stderr)
    if m8 != t8:
        ok = False
    if args.dry_run:
        print("  (dry-run)", file=sys.stderr); return
    if not ok:
        print("  ⚠ 확정 불일치 — 미저장.", file=sys.stderr); return
    rp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → 저장 {rp.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
