"""data.go.kr 당선인 정보 API → 기초의원 지역구(tc=6) 당선인 '확정' 회수.

중선거구(1선거구 2~4명) magnitude를 추정(infer_council_winners.py)하던 것을,
NEC 확정 당선인 명부로 교체한다. sggName(선거구)·name 매칭으로 won 플래그를
실제값으로 set + race.seats_total = 실제 정수.

데이터 위치: tc=6 race는 9회 main, 5~8회 .sigungu.json chunk.
9회(2026)는 선거 직후 OpenAPI 미게시(INFO-03) → NEC 게시 후 재실행.

사용:
  NEC_API_KEY=... .venv/bin/python scripts/fetch/fetch_council_winners.py --n 8
  (--n 5/6/7/8/9)
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
SGID = {5: "20100602", 6: "20140604", 7: "20180613", 8: "20220601", 9: "20260603"}
ORD = {5: "5th", 6: "6th", 7: "7th", 8: "8th", 9: "9th"}
YEAR = {5: 2010, 6: 2014, 7: 2018, 8: 2022, 9: 2026}

# 시도명 시대차 정규화 — 우리 데이터(현행)·API(선거 당시)를 한 키로.
_SIDO_CANON = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"}
_SUF = re.compile(r"(?:제\d+|[가-하])선거구$")
# 통합시 일반구(수원시장안구)는 데이터마다 parent(수원시)/일반구 혼재 → parent 시로 통일.
_PARENT_GU = re.compile(r"^([가-힣]+시)[가-힣]+구$")


def norm(s: str) -> str:
    return (s or "").replace(" ", "").strip()


def canon_sido(s: str) -> str:
    s = norm(s)
    return _SIDO_CANON.get(s, s)


def parent_city(sg: str) -> str:
    m = _PARENT_GU.match(sg)
    return m.group(1) if m else sg


def fetch_winners(key: str, sg_id: str):
    """tc=6 당선인 → {(canon sido, norm wiwName=시군구): set(norm name)} + 총수.
    선거구(sggName)가 아닌 시군구(wiwName)로 그룹 → 선거구명 표기차 무관, 이름으로 매칭."""
    out = defaultdict(set)
    page, total = 1, 0
    while True:
        url = (f"{API}?serviceKey={key}&sgId={sg_id}&sgTypecode=6"
               f"&pageNo={page}&numOfRows=100")
        root = ET.fromstring(urllib.request.urlopen(url, timeout=40).read())
        if root.findtext("header/resultCode") != "INFO-00":
            break
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            sido = it.findtext("sdName") or ""
            wiw = it.findtext("wiwName") or ""
            nm = it.findtext("name") or ""
            if sido and wiw and nm:
                out[(canon_sido(sido), parent_city(norm(wiw)))].add(norm(nm))
        total = int(root.findtext("body/totalCount") or 0)
        if page * 100 >= total:
            break
        page += 1
    return out, total


# API 시도명(선거 당시) → 우리 데이터 현행명(render-winners SIDO_ORDER·hex 레이아웃 기준).
_API_TO_CURRENT = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도"}


def fetch_winners_full(key: str, sg_id: str):
    """tc=6 당선인 전체 필드 리스트 (재구성용)."""
    out, page, total = [], 1, 0
    while True:
        url = (f"{API}?serviceKey={key}&sgId={sg_id}&sgTypecode=6"
               f"&pageNo={page}&numOfRows=100")
        root = ET.fromstring(urllib.request.urlopen(url, timeout=40).read())
        if root.findtext("header/resultCode") != "INFO-00":
            break
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            sd = (it.findtext("sdName") or "").strip()
            out.append({
                "sido": _API_TO_CURRENT.get(sd, sd),
                "sigungu": (it.findtext("wiwName") or "").strip(),
                "district": (it.findtext("sggName") or "").strip(),
                "name": (it.findtext("name") or "").strip(),
                "party": (it.findtext("jdName") or "무소속").strip(),
                "votes": int(it.findtext("dugsu") or 0),
                "pct": round(float(it.findtext("dugyul") or 0), 2),
            })
        total = int(root.findtext("body/totalCount") or 0)
        if page * 100 >= total:
            break
        page += 1
    return out, total


def rebuild_tc6(n: int, winners):
    """당선인 리스트 → tc=6 race 재구성. 기존 tc=6 제거 후 교체. (당선인만, 낙선자 없음.)"""
    from collections import defaultdict
    by_race = defaultdict(list)
    for w in winners:
        by_race[(w["sido"], w["sigungu"], w["district"])].append(w)
    new_races = []
    for (sido, sigungu, district), ws in sorted(by_race.items()):
        ws.sort(key=lambda x: -x["votes"])
        # seats:1 — won 기반(render-winners)·seats 기반(의회 hex·local.js) 카운터 모두 호환.
        cands = [{"name": w["name"], "party": w["party"], "votes": w["votes"],
                  "pct": w["pct"], "rank": i + 1, "won": True, "seats": 1} for i, w in enumerate(ws)]
        new_races.append({"sg_typecode": "6", "sido": sido, "sigungu": sigungu,
                          "scope": "district", "district": district,
                          "candidates": cands, "seats_total": len(cands)})
    main_f = ROOT / f"data/results/{ORD[n]}-local-{YEAR[n]}.json"
    sgg_f = ROOT / f"data/results/{ORD[n]}-local-{YEAR[n]}.sigungu.json"
    target = main_f
    if not any(r.get("sg_typecode") == "6" for r in json.loads(main_f.read_text())["races"]):
        target = sgg_f
    d = json.loads(target.read_text(encoding="utf-8"))
    old = sum(1 for r in d["races"] if r.get("sg_typecode") == "6")
    d["races"] = [r for r in d["races"] if r.get("sg_typecode") != "6"] + new_races
    target.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    seats = sum(len(r["candidates"]) for r in new_races)
    print(f"  재구성: tc=6 race {old}→{len(new_races)}, 당선 {seats}명 → {target.name}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True, help="지선 회차 5/6/7/8/9")
    ap.add_argument("--force", action="store_true", help="매칭률 낮아도 강제 저장")
    ap.add_argument("--rebuild", action="store_true",
                    help="tc=6 race를 당선인 API로 재구성(기존 교체·당선자만). 후보 누락 회차용.")
    args = ap.parse_args()
    key = os.environ.get("NEC_API_KEY")
    if not key:
        print("ERR: NEC_API_KEY 환경변수 필요", file=sys.stderr)
        sys.exit(1)
    n = args.n
    if n not in SGID:
        print(f"ERR: 미지원 회차 {n}", file=sys.stderr)
        sys.exit(1)

    if args.rebuild:
        winners, total = fetch_winners_full(key, SGID[n])
        if not winners:
            print(f"{n}회: API 당선인 없음(INFO-03 — 미게시?). skip.", file=sys.stderr)
            return
        print(f"{n}회 기초의원 당선인 API: {total}명 (재구성 모드)", file=sys.stderr)
        rebuild_tc6(n, winners)
        return

    wset, total = fetch_winners(key, SGID[n])
    if not wset:
        print(f"{n}회: API 당선인 없음(INFO-03 — 미게시?). 휴리스틱 유지, skip.", file=sys.stderr)
        return
    print(f"{n}회 기초의원 당선인 API: {total}명 · {len(wset)}개 선거구", file=sys.stderr)

    # tc=6 race가 든 결과 파일 선택 (9회 main / 5~8회 sigungu chunk)
    main_f = ROOT / f"data/results/{ORD[n]}-local-{YEAR[n]}.json"
    sgg_f = ROOT / f"data/results/{ORD[n]}-local-{YEAR[n]}.sigungu.json"
    target = main_f
    if not any(r.get("sg_typecode") == "6" for r in json.loads(main_f.read_text())["races"]):
        target = sgg_f
    d = json.loads(target.read_text(encoding="utf-8"))

    def race_sigungu(r):
        if r.get("sigungu"):
            return r["sigungu"]
        return _SUF.sub("", r.get("district") or "")

    marked = unmatched = 0
    by_party = defaultdict(int)
    for r in d.get("races", []):
        if r.get("sg_typecode") != "6":
            continue
        names = wset.get((canon_sido(r.get("sido")), parent_city(norm(race_sigungu(r)))))
        if not names:
            unmatched += 1
            continue
        won_here = 0
        for c in (r.get("candidates") or []):
            # 같은 시군구 당선자 집합에 이름이 있으면 당선(선거구는 시군구 내 이름 유일).
            won = norm(c.get("name")) in names
            c["won"] = won
            if won:
                marked += 1
                won_here += 1
                by_party[c.get("party") or "무소속"] += 1
        r["seats_total"] = won_here
    # 안전 가드 — 매칭률 낮으면(옛 데이터 이름 표기차 등) 저장 안 함(휴리스틱 유지).
    rate = marked / total if total else 0
    if rate < 0.97 and not args.force:
        print(f"  ⚠ 매칭 {marked}/{total} ({rate:.1%}) <97% — 이름·표기 불일치로 누락. "
              f"미저장(휴리스틱 유지). 강제하려면 --force.", file=sys.stderr)
        return
    target.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  확정 마킹 {marked}명 ({rate:.1%}) · 매칭 실패 race {unmatched} → {target.name}", file=sys.stderr)
    for p, c in sorted(by_party.items(), key=lambda x: -x[1])[:8]:
        print(f"    {p}: {c}", file=sys.stderr)


if __name__ == "__main__":
    main()
