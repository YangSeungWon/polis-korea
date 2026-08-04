"""info.nec.go.kr VCCP09 개표현황 → 광역의회 비례(electionCode=8) 시도별 득표 + 당선인 API 의석.

fetch_metro_prop_old(의석만, votes_pending)를 대체 — 시도별 개표(정당 득표수·득표율·선거인수·
투표수·무효·기권)를 VCCP09에서 받고, 의석은 NEC 당선인 API(sgTypecode=8)로 받아 합쳐
완전한 proportional_sido race를 만든다. 정당명은 그 선거 표기로 정규화(election-aware + override).

사용: NEC_API_KEY는 .env. python scripts/fetch/fetch_metro_prop_votes.py [--n 3] [--dry-run]
의존: pandas, lxml.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
WINNER_API = "https://apis.data.go.kr/9760000/WinnerInfoInqireService2/getWinnerInfoInqire"
VCCP_URL = "https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml"

ELECTIONS = {3: ("3rd-local-2002", "20020613"), 4: ("4th-local-2006", "20060531")}
OVERRIDE = {4: {"민주당": "민주당(2005)"}}

# 시도 핵심명 → NEC cityCode. by_sido(당선인 API sdName)를 핵심명으로 정규화해 매칭.
CITYCODE = {
    "서울": "1100", "부산": "2600", "대구": "2700", "인천": "2800", "광주": "2900",
    "대전": "3000", "울산": "3100", "경기": "4100", "강원": "4200",
    "충청북": "4300", "충청남": "4400", "전라북": "4500", "전라남": "4600",
    "경상북": "4700", "경상남": "4800", "제주": "5000",
}
NON_PARTY_LEAF = {"구시군명", "선거인수", "투표수", "계", "무효투표수", "무효 투표수", "기권자수"}


def sido_core(name: str) -> str:
    for suf in ("특별자치도", "특별자치시", "특별시", "광역시", "도"):
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


def load_key() -> str:
    key = os.environ.get("NEC_API_KEY")
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("NEC_API_KEY"):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("NEC_API_KEY 없음")
    return key


def alias_map() -> dict:
    reg = json.loads((ROOT / "data/parties/registry.json").read_text()).get("parties", {})
    m = {}
    for name, info in reg.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        if info.get("abbr"):
            m[info["abbr"]] = name
        for a in info.get("aliases", []):
            m[a] = name
    return m


def make_canon(existing: set, override: dict):
    al = alias_map()

    def cf(p):
        if p in override:
            return override[p]
        if p in existing:
            return p
        c = al.get(p)
        return c if (c and c in existing) else p
    return cf


def fetch_seats(key: str, sg_id: str) -> dict:
    """sgTypecode=8 당선인 → {sido_core: {party: seats}}."""
    out = defaultdict(lambda: defaultdict(int))
    page = 1
    while True:
        url = f"{WINNER_API}?serviceKey={key}&sgId={sg_id}&sgTypecode=8&pageNo={page}&numOfRows=100&resultType=xml"
        root = ET.fromstring(urllib.request.urlopen(url, timeout=40).read())
        if root.findtext("header/resultCode") != "INFO-00":
            break
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            sido = sido_core((it.findtext("sdName") or "").strip())
            party = (it.findtext("jdName") or "").strip()
            if sido and party:
                out[sido][party] += 1
        if page * 100 >= int(root.findtext("body/totalCount") or 0):
            break
        page += 1
    return out


def fetch_votes(election_name: str, city_code: str) -> dict | None:
    """VCCP09 시도 개표 → {electors, voters, invalid, abstain, valid, parties:{p:(votes,pct)}}."""
    data = urllib.parse.urlencode({
        "electionId": "0000000000", "requestURI": "/electioninfo/0000000000/vc/vccp09.jsp",
        "topMenuId": "VC", "secondMenuId": "VCCP09", "menuId": "VCCP09", "statementId": "VCCP09_#8",
        "oldElectionType": "1", "electionType": "4", "electionName": election_name, "electionCode": "8",
        "cityCode": city_code, "townCode": "-1", "sggCityCode": "-1"}).encode()
    req = urllib.request.Request(VCCP_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    tables = pd.read_html(StringIO(html))
    leaf = lambda c: (c[-1] if isinstance(c, tuple) else c)
    t = None
    for x in tables:
        leaves = [leaf(c) for c in x.columns]
        if "선거인수" in leaves and any(l not in NON_PARTY_LEAF for l in leaves):
            t = x; break
    if t is None or len(t) < 2:
        return None
    cols = list(t.columns)
    col_by_leaf = {leaf(c): c for c in cols}
    r0, r1 = t.iloc[0], t.iloc[1]  # 합계(득표수), 득표율

    def num(v):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 0
    parties = {}
    for c in cols:
        lf = leaf(c)
        if lf in NON_PARTY_LEAF:
            continue
        parties[lf] = (num(r0[c]), float(r1[c]) if pd.notna(r1[c]) else None)
    g = lambda name: num(r0[col_by_leaf[name]]) if name in col_by_leaf else 0
    invalid = g("무효투표수") or g("무효 투표수")
    return {
        "electors": g("선거인수"), "voters": g("투표수"),
        "valid": g("계"), "invalid": invalid, "abstain": g("기권자수"),
        "parties": parties,
    }


def build_race(sido_full, votes, seats_map, canon):
    cands = []
    for party_raw, (v, pct) in votes["parties"].items():
        party = canon(party_raw)
        cands.append({"name": party, "party": party, "votes": v, "pct": pct,
                      "seats": seats_map.get(party_raw, seats_map.get(party, 0))})
    cands.sort(key=lambda c: -(c["votes"] or 0))
    for i, c in enumerate(cands):
        c["rank"] = i + 1
        c["won"] = c["seats"] > 0
    return {
        "sg_typecode": "8", "sido": sido_full, "sigungu": "", "scope": "proportional_sido",
        "electors": votes["electors"], "voters": votes["voters"],
        "valid_votes": votes["valid"], "invalid_votes": votes["invalid"], "abstain": votes["abstain"],
        "seats_total": sum(seats_map.values()), "candidates": cands,
    }


def backfill(n, key, dry):
    fid, sg_id = ELECTIONS[n]
    path = RESULTS / f"{fid}.json"
    data = json.loads(path.read_text())
    existing = {c.get("party") for r in data.get("races", []) if r.get("sg_typecode") != "8"
                for c in (r.get("candidates") or []) if c.get("party")}
    canon = make_canon(existing, OVERRIDE.get(n, {}))
    seats = fetch_seats(key, sg_id)
    # 당선인 API에 등장한 시도 = 비례 있는 시도. 각 시도 sdName(full) 보존을 위해 다시 조회 필요 →
    # 여기선 by sido_core로 cityCode 찾고, sido full명은 데이터의 광역장 race에서 가져온다.
    full_by_core = {}
    for r in data.get("races", []):
        if r.get("sg_typecode") == "3" and r.get("sido"):
            full_by_core[sido_core(r["sido"])] = r["sido"]
    races = [r for r in data.get("races", []) if r.get("sg_typecode") != "8"]
    new, tot_v, tot_s = [], 0, 0
    for core, seats_map in seats.items():
        cc = CITYCODE.get(core)
        full = full_by_core.get(core, core)
        if not cc:
            print(f"  ! cityCode 없음: {core}"); continue
        votes = fetch_votes(sg_id, cc)
        if not votes:
            # 제주 등 VCCP09 무투표/구조차이 — 의석만(votes_pending).
            cands = [{"name": canon(p), "party": canon(p), "votes": None, "pct": None,
                      "seats": s, "won": True, "rank": i + 1}
                     for i, (p, s) in enumerate(sorted(seats_map.items(), key=lambda x: -x[1]))]
            race = {"sg_typecode": "8", "sido": full, "sigungu": "", "scope": "proportional_sido",
                    "votes_pending": True, "seats_total": sum(seats_map.values()), "candidates": cands}
            print(f"  · {core}: 개표 미상 → 의석만({race['seats_total']}석)")
        else:
            race = build_race(full, votes, seats_map, canon)
            tot_v += sum(v for v, _ in votes["parties"].values())
        new.append(race)
        tot_s += race["seats_total"]
    races.extend(new)
    data["races"] = races
    nat = defaultdict(int)
    for r in new:
        for c in r["candidates"]:
            nat[c["party"]] += c["votes"] or 0
    summ = " · ".join(f"{p} {v:,}" for p, v in sorted(nat.items(), key=lambda x: -x[1])[:5])
    print(f"  {fid}: {len(new)}시도 · {tot_s}석 · 총득표 {tot_v:,} — {summ}{' [dry]' if dry else ''}")
    if not dry:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = load_key()
    for n in ([args.n] if args.n else list(ELECTIONS)):
        backfill(n, key, args.dry_run)


if __name__ == "__main__":
    main()
