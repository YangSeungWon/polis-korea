"""info.nec.go.kr 당선인 명부(EPEI01) → 기초의원 지역구(tc=6) 확정 당선인 회수.

OpenAPI(WinnerInfoInqire)가 선거 직후 미게시(INFO-03)일 때, NEC 개표방송 포털의
'당선인 명부'(secondMenuId=EPEI01, statementId=EPEI01_#6)는 확정 당선인을 즉시 제공.
중선거구 magnitude 추정(infer_council_winners.py)을 실제 당선인 명부로 교체:
선거구(SGGNAME)·이름 매칭으로 won 플래그·seats_total을 확정값으로 set.

사용:
  .venv/bin/python scripts/fetch/fetch_council_winners_live.py            # 9회 기본
  .venv/bin/python scripts/fetch/fetch_council_winners_live.py --dry-run  # 저장 안 함
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://info.nec.go.kr"
SHOW = "/m/main/showDocument.xhtml"
REPORT = "/m/electioninfo/electionInfo_report.json"
CITYBOX = "/m/bizcommon/selectbox/selectbox_cityCodeBySgJson.json"

# 회차 → NEC electionId (00 + 선거일)
ELECTION_ID = {9: "0020260603"}
RESULTS = {9: "data/results/9th-local-2026.json"}

_SIDO_CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도"}


def norm(s: str) -> str:
    return (s or "").replace(" ", "").strip()


def canon_sido(s: str) -> str:
    return _SIDO_CANON.get(norm(s), norm(s))


def make_session(election_id: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    s.get(f"{BASE}{SHOW}", params={"electionId": election_id, "topMenuId": "EP",
                                   "secondMenuId": "EPEI01"}, timeout=20)
    return s


def _to_int(s) -> int:
    try:
        return int(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def fetch_winners(election_id: str):
    """EPEI01_#6 시도별 호출 → {(canon sido, norm 선거구): [winner dict, ...]}.
    winner dict = {name, party, votes, uncontested, sido, sigungu, district}."""
    s = make_session(election_id)
    rc = s.get(f"{BASE}{CITYBOX}", params={"electionId": election_id, "electionCode": "6"}, timeout=20)
    cities = rc.json().get("jsonResult", {}).get("body") or []
    by_sgg: dict[tuple, list] = defaultdict(list)
    total = 0
    for c in cities:
        code = str(c.get("CODE"))
        data = {"electionId": election_id, "secondMenuId": "EPEI01", "topMenuId": "EP",
                "statementId": "EPEI01_#6", "electionCode": "6",
                "cityCode": code, "sggCityCode": "-1", "townCode": "-1"}
        r = s.post(f"{BASE}{REPORT}", data=data, timeout=30)
        body = r.json().get("jsonResult", {}).get("body") or []
        for row in body:
            sido = canon_sido(row.get("SDNAME", ""))
            sgg = norm(row.get("SGGNAME", ""))
            nm = norm(row.get("K_NAME", ""))
            party = (row.get("JDNAME") or "무소속").strip()
            dugsu = (row.get("DUGSU") or "").strip()
            unc = "무투표" in dugsu
            if sido and sgg and nm:
                by_sgg[(sido, sgg)].append({
                    "name": nm, "party": party, "votes": _to_int(dugsu),
                    "uncontested": unc, "sido": (row.get("SDNAME") or "").strip(),
                    "sigungu": (row.get("WIWNAME") or "").strip(),
                    "district": (row.get("SGGNAME") or "").strip(),
                })
                total += 1
    return by_sgg, total


def fetch_prop_seats(election_id: str):
    """EPEI01_#9 비례 당선인 명부 → {(canon sido, norm 시군구): {정당: 의석수}}.
    비례 row는 SDNAME=None·SGGNAME=시군구 → 시도는 조회한 cityCode(NAME)로 추적."""
    s = make_session(election_id)
    rc = s.get(f"{BASE}{CITYBOX}", params={"electionId": election_id, "electionCode": "9"}, timeout=20)
    cities = rc.json().get("jsonResult", {}).get("body") or []
    by_sgg: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    total = 0
    for c in cities:
        sido = canon_sido(c.get("NAME", ""))
        data = {"electionId": election_id, "secondMenuId": "EPEI01", "topMenuId": "EP",
                "statementId": "EPEI01_#9", "electionCode": "9",
                "cityCode": str(c.get("CODE")), "sggCityCode": "-1", "townCode": "-1"}
        r = s.post(f"{BASE}{REPORT}", data=data, timeout=30)
        for row in r.json().get("jsonResult", {}).get("body") or []:
            sgg = norm(row.get("SGGNAME", ""))
            party = (row.get("JDNAME") or "무소속").strip()
            if sgg:
                by_sgg[(sido, sgg)][party] += 1
                total += 1
    return by_sgg, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=9)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="매칭률 낮아도 저장")
    args = ap.parse_args()
    n = args.n
    eid = ELECTION_ID[n]
    by_sgg, total = fetch_winners(eid)
    print(f"{n}회 기초의원 당선인 명부(EPEI01): {total}명 · {len(by_sgg)}개 선거구", file=sys.stderr)
    if total == 0:
        print("  ! 당선인 0명 — 엔드포인트/회차 확인 필요. skip.", file=sys.stderr)
        return

    rp = ROOT / RESULTS[n]
    d = json.loads(rp.read_text(encoding="utf-8"))

    marked = matched_races = name_miss = 0
    by_party: dict[str, int] = defaultdict(int)
    seen_keys = set()
    for r in d.get("races", []):
        if r.get("sg_typecode") != "6":
            continue
        key = (canon_sido(r.get("sido")), norm(r.get("district") or ""))
        winners = by_sgg.get(key)
        if not winners:
            continue   # 명부에 없는 선거구 (이론상 없음) — 그대로 둠
        seen_keys.add(key)
        matched_races += 1
        wnames = {w["name"] for w in winners}
        for c in (r.get("candidates") or []):
            won = norm(c.get("name")) in wnames
            c["won"] = won
            if won:
                marked += 1
                by_party[c.get("party") or "무소속"] += 1
        r["seats_total"] = len(winners)   # 명부의 당선인 수 = 실제 정수
        got = {norm(c.get("name")) for c in r["candidates"] if c.get("won")}
        name_miss += len(wnames - got)

    # 개표 데이터에 없던 선거구(거의 무투표) → 당선인만으로 race 추가.
    added_races = added_cands = 0
    insert_at = max((i for i, r in enumerate(d["races"]) if r.get("sg_typecode") == "6"), default=len(d["races"])) + 1
    new_races = []
    for key, winners in by_sgg.items():
        if key in seen_keys:
            continue
        w0 = winners[0]
        cands = [{"name": w["name"], "party": w["party"], "votes": w["votes"],
                  "rank": i + 1, "won": True, "is_uncontested": w["uncontested"]}
                 for i, w in enumerate(winners)]
        new_races.append({
            "sg_typecode": "6", "sido": _SIDO_CANON.get(w0["sido"], w0["sido"]),
            "sigungu": w0["sigungu"], "scope": "district", "district": w0["district"],
            "count_pct": 100.0, "is_uncontested": all(w["uncontested"] for w in winners),
            "candidates": cands, "seats_total": len(winners),
        })
        added_races += 1
        added_cands += len(winners)
        for w in winners:
            by_party[w["party"]] += 1
    d["races"][insert_at:insert_at] = new_races

    # === tc9 비례 — 명부(EPEI01_#9)로 정당별 의석 교체 (calc_proportional 추정 대체) ===
    prop, prop_total = fetch_prop_seats(eid)
    prop_seen, prop_marked = set(), 0
    prop_party: dict[str, int] = defaultdict(int)
    for r in d.get("races", []):
        if r.get("sg_typecode") != "9":
            continue
        key = (canon_sido(r.get("sido")), norm(r.get("sigungu") or ""))
        seats_map = prop.get(key)
        if not seats_map:
            continue
        prop_seen.add(key)
        for c in (r.get("candidates") or []):
            sv = seats_map.get(c.get("party"), 0)
            c["seats"] = sv
            c["won"] = sv > 0
            if sv:
                prop_marked += sv
                prop_party[c.get("party")] += sv
        r["seats_total"] = sum(seats_map.values())
    # 개표방송(VCCP09)에 비례 득표가 아직 없는 시군구(MAGAM=0 미마감) → 명부의 확정 의석만
    # 추가. 득표는 NEC 미게시라 votes 미설정 + votes_pending 플래그(OpenAPI 게시 후 백필).
    # 가짜 0표를 넣지 않음 — 의석은 정확, 득표는 '없음'을 명시.
    prop_added = 0
    p_insert = max((i for i, r in enumerate(d["races"]) if r.get("sg_typecode") == "9"), default=len(d["races"])) + 1
    p_new = []
    for (sido, sgg), seats_map in prop.items():
        if (sido, sgg) in prop_seen:
            continue
        cands = [{"party": p, "seats": sv, "won": True}
                 for p, sv in sorted(seats_map.items(), key=lambda x: -x[1])]
        p_new.append({"sg_typecode": "9", "sido": sido, "sigungu": sgg,
                      "scope": "proportional_sigungu", "seats_total": sum(seats_map.values()),
                      "votes_pending": True, "candidates": cands})
        prop_added += 1
        for p, sv in seats_map.items():
            prop_party[p] += sv
            prop_marked += sv
    d["races"][p_insert:p_insert] = p_new

    total_marked = marked + added_cands
    rate = total_marked / total if total else 0
    print(f"[tc6 지역구] 매칭 선거구 {matched_races} · 추가(무투표) 선거구 {added_races} ({added_cands}명)", file=sys.stderr)
    print(f"  확정 당선 {total_marked}/{total} ({rate:.1%}) · 이름불일치 {name_miss}", file=sys.stderr)
    for p, c in sorted(by_party.items(), key=lambda x: -x[1]):
        print(f"    {p}: {c}", file=sys.stderr)
    print(f"[tc9 비례] 명부 {prop_total}석 · 매칭 시군구 {len(prop_seen)} · 추가(개표미마감) 시군구 {prop_added}", file=sys.stderr)
    print(f"  확정 의석 {prop_marked}/{prop_total} ({prop_marked / prop_total:.1%})", file=sys.stderr)
    for p, c in sorted(prop_party.items(), key=lambda x: -x[1]):
        print(f"    {p}: {c}", file=sys.stderr)
    if args.dry_run:
        print("  (dry-run — 저장 안 함)", file=sys.stderr)
        return
    if (rate < 0.999 or prop_marked != prop_total) and not args.force:
        print(f"  ⚠ 확정률 미달 — 미저장. --force로 강제.", file=sys.stderr)
        return
    rp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → 저장 {rp.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
