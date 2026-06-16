"""info.nec.go.kr VCCP09(electionCode=9) → 기초의원 비례 시군구별 득표를 기존 의석 race에 보강.

fetch_council_prop이 채운 4회 기초 비례(tc=9, 의석만 votes_pending)에 시군구별 정당 득표수·
득표율·선거인수·투표수·무효를 더한다. VCCP09는 시도(cityCode) 1쿼리에 그 시도 시군구를
3행 블록(정당명 / 득표수 / 득표율)으로 준다 — 16쿼리. 시군구명으로 기존 race에 매칭.

사용: python scripts/fetch/fetch_council_prop_votes.py [--n 4] [--dry-run]
의존: pandas, lxml.
"""
from __future__ import annotations
import argparse
import json
import re
import urllib.request
import urllib.parse
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
VCCP_URL = "https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml"
ELECTIONS = {4: ("4th-local-2006", "20060531")}
OVERRIDE = {4: {"민주당": "민주당(2005)"}}

# NEC cityCode → 데이터 sido 핵심명 (역방향은 데이터의 sido full에서 가져옴)
SIDO_CITY = {
    "서울특별시": "1100", "부산광역시": "2600", "대구광역시": "2700", "인천광역시": "2800",
    "광주광역시": "2900", "대전광역시": "3000", "울산광역시": "3100", "경기도": "4100",
    "강원도": "4200", "충청북도": "4300", "충청남도": "4400", "전라북도": "4500",
    "전라남도": "4600", "경상북도": "4700", "경상남도": "4800", "제주도": "5000",
}


def alias_map():
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


def make_canon(existing, override):
    al = alias_map()

    def cf(p):
        if p in override:
            return override[p]
        if p in existing:
            return p
        c = al.get(p)
        return c if (c and c in existing) else p
    return cf


def norm_sgg(name: str) -> str:
    """시군구명 매칭용 — 공백 제거. 통합시 일반구는 그대로(데이터도 동일 표기 가정)."""
    return re.sub(r"\s+", "", name or "")


def num(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def fetch_sido(election_name: str, city_code: str) -> dict:
    """{norm 시군구명: {electors,voters,valid,invalid,parties:{party:(votes,pct)}}}."""
    data = urllib.parse.urlencode({
        "electionId": "0000000000", "requestURI": "/electioninfo/0000000000/vc/vccp09.jsp",
        "topMenuId": "VC", "secondMenuId": "VCCP09", "menuId": "VCCP09", "statementId": "VCCP09_#9",
        "oldElectionType": "1", "electionType": "4", "electionName": election_name, "electionCode": "9",
        "cityCode": city_code, "townCode": "-1", "sggCityCode": "-1"}).encode()
    req = urllib.request.Request(VCCP_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    tables = pd.read_html(StringIO(html))
    t = None
    for x in tables:
        if x.shape[1] >= 9 and "선거구명" in [str(c[0]) if isinstance(c, tuple) else str(c) for c in x.columns]:
            t = x; break
    if t is None or len(t) < 3:
        return {}
    cols = list(t.columns)
    # 컬럼 위치: 0 선거구명, 1 구시군명, 2 선거인수, 3 투표수, 4..n-2 정당+계, n-2 무효, n-1 기권
    party_cols = cols[4:-2]
    out = {}
    i = 0
    while i + 2 < len(t):
        names = t.iloc[i]      # 정당명 행
        vals = t.iloc[i + 1]   # 득표수 행
        pcts = t.iloc[i + 2]   # 득표율 행
        sgg = names[cols[0]]
        if not isinstance(sgg, str) or not sgg.strip():
            i += 1; continue
        parties = {}
        valid = 0
        for c in party_cols:
            pname = names[c]
            if not isinstance(pname, str):
                continue
            if pname == "계":
                valid = num(vals[c]); continue
            parties[pname] = (num(vals[c]), float(pcts[c]) if pd.notna(pcts[c]) else None)
        if parties:
            out[norm_sgg(sgg)] = {
                "electors": num(vals[cols[2]]), "voters": num(vals[cols[3]]),
                "valid": valid, "invalid": num(vals[cols[-2]]), "abstain": num(vals[cols[-1]]),
                "parties": parties,
            }
        i += 3
    return out


def backfill(n, dry):
    fid, sg_id = ELECTIONS[n]
    path = RESULTS / f"{fid}.sigungu.json"
    data = json.loads(path.read_text())
    existing = {c.get("party") for r in data.get("races", []) for c in (r.get("candidates") or []) if c.get("party")}
    canon = make_canon(existing, OVERRIDE.get(n, {}))

    # 시도별 개표 수집
    by_sido = {}
    for sido_full, cc in SIDO_CITY.items():
        try:
            by_sido[sido_full] = fetch_sido(sg_id, cc)
        except Exception as e:
            print(f"  ! {sido_full} 개표 실패: {e}")
            by_sido[sido_full] = {}

    matched = unmatched = 0
    for r in data.get("races", []):
        if r.get("sg_typecode") != "9":
            continue
        sido = r.get("sido", "")
        sgg = norm_sgg(r.get("sigungu", ""))
        votes = by_sido.get(sido, {}).get(sgg)
        if not votes:
            unmatched += 1
            continue
        matched += 1
        # 기존 후보(의석)에 득표 주입 + 누락 정당 추가
        cand_by_party = {c["party"]: c for c in r.get("candidates", [])}
        for praw, (v, pct) in votes["parties"].items():
            party = canon(praw)
            c = cand_by_party.get(party)
            if c:
                c["votes"] = v; c["pct"] = pct
            else:
                r.setdefault("candidates", []).append(
                    {"name": party, "party": party, "votes": v, "pct": pct, "seats": 0, "won": False})
        r["electors"] = votes["electors"]; r["voters"] = votes["voters"]
        r["valid_votes"] = votes["valid"]; r["invalid_votes"] = votes["invalid"]; r["abstain"] = votes["abstain"]
        r.pop("votes_pending", None)
        r["candidates"].sort(key=lambda c: -(c.get("votes") or 0))
        for i, c in enumerate(r["candidates"]):
            c["rank"] = i + 1

    print(f"  {fid} 기초비례: 득표 매칭 {matched} · 미매칭 {unmatched}{' [dry]' if dry else ''}")
    if not dry and matched:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    backfill(args.n, args.dry_run)


if __name__ == "__main__":
    main()
