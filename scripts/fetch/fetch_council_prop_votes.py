"""info.nec.go.kr VCCP09(electionCode=9) → 기초의원 비례 **시군구별 득표**를 의석 race에 보강.

당선인 API(fetch_council_prop / fetch_council_winners_live)는 의석만 준다. 득표는
개표현황(VCCP09)에만 있다 — 없으면 '기초의원 비례 시·군·구별 표심' 지도가 통째로 빈다.

## 회차를 하드코딩하지 않는다

이 스크립트는 원래 4회 한 회차만 박혀 있었고(`ELECTIONS = {4: ...}`), 그래서 5~8회는
**가져올 수 있는데 안 가져온 상태**로 남아 있었다. 화면에는 '자료 없음'으로 보였다.
가져올 수 있는 것을 없다고 말하지 않기 위해 전 회차를 대상으로 돌린다.

## 시도 코드는 회차마다 다르다

강원(4200→5200)·전북(4500→5300)처럼 특별자치도 전환으로 코드가 바뀐다. 코드표를
손으로 관리하면 조용히 한 시도가 통째로 빠진다 — 후보 코드를 **훑어서 응답이 있는
것만** 쓴다.

사용: python scripts/fetch/fetch_council_prop_votes.py [--n 5 6 7 8 9] [--dry-run]
의존: pandas, lxml.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.request
import urllib.parse
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
VCCP_URL = "https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml"
ELECTIONS = {
    4: ("4th-local-2006", "20060531"), 5: ("5th-local-2010", "20100602"),
    6: ("6th-local-2014", "20140604"), 7: ("7th-local-2018", "20180613"),
    8: ("8th-local-2022", "20220601"), 9: ("9th-local-2026", "20260603"),
}
OVERRIDE = {4: {"민주당": "민주당(2005)"}}

# 후보 cityCode — 회차마다 유효한 것만 응답한다. 이름은 응답에서 오는 게 아니라
# 우리 데이터의 sido와 맞춰야 하므로 (코드 → 데이터 sido 후보) 로 둔다.
CITY_CODES = {
    "1100": ["서울특별시"], "2600": ["부산광역시"], "2700": ["대구광역시"],
    "2800": ["인천광역시"], "2900": ["광주광역시"], "3000": ["대전광역시"],
    "3100": ["울산광역시"], "3600": ["세종특별자치시"], "4100": ["경기도"],
    "4200": ["강원도", "강원특별자치도"], "5200": ["강원특별자치도", "강원도"],
    "4300": ["충청북도"], "4400": ["충청남도"],
    "4500": ["전라북도", "전북특별자치도"], "5300": ["전북특별자치도", "전라북도"],
    "4600": ["전라남도"], "4700": ["경상북도"], "4800": ["경상남도"],
    "5000": ["제주도", "제주특별자치도"],
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
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
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


def target_path(fid: str) -> Path:
    """tc9 행이 실제로 들어 있는 파일. 5~8회는 .sigungu 청크, 9회는 본 파일이다."""
    chunk = RESULTS / f"{fid}.sigungu.json"
    if chunk.exists():
        d = json.loads(chunk.read_text())
        if any(r.get("sg_typecode") == "9" for r in d.get("races", [])):
            return chunk
    return RESULTS / f"{fid}.json"


def backfill(n, dry):
    fid, sg_id = ELECTIONS[n]
    path = target_path(fid)
    if not path.exists():
        print(f"  ! {fid}: 결과 파일 없음"); return
    data = json.loads(path.read_text())
    rows = [r for r in data.get("races", []) if r.get("sg_typecode") == "9"
            and r.get("scope") == "proportional_sigungu"]
    if not rows:
        print(f"  ! {fid}: tc9 행 없음 ({path.name})"); return
    existing = {c.get("party") for r in data.get("races", []) for c in (r.get("candidates") or []) if c.get("party")}
    canon = make_canon(existing, OVERRIDE.get(n, {}))
    sidos = {r.get("sido", "") for r in rows}

    # 시도별 개표 수집 — 응답이 있는 코드만 채택(회차마다 코드가 다르다).
    #
    # **한 파일 안에 시도 표기가 섞여 있다.** 8회 결과에 '강원도'와 '강원특별자치도'가
    # 같이 들어 있어, 코드를 첫 이름 하나에만 저장했더니 나머지 17곳이 통째로 결손이
    # 됐다. 그 코드가 대응하는 **모든 표기**에 같은 응답을 건다.
    by_sido: dict = {}
    for cc, cands in CITY_CODES.items():
        hits = [s for s in cands if s in sidos and s not in by_sido]
        if not hits:
            continue
        try:
            got = fetch_sido(sg_id, cc)
        except Exception as e:                                   # noqa: BLE001
            print(f"  ! {'·'.join(hits)}({cc}) 개표 실패: {e}"); got = {}
        for h in hits:
            if got:
                by_sido[h] = got

    before = sum(1 for r in rows
                 if any(c.get("party") and (c.get("votes") or 0) > 0 for c in (r.get("candidates") or [])))
    matched = unmatched = 0
    for r in rows:
        sido = r.get("sido", "")
        sgg = norm_sgg(r.get("sigungu", ""))
        votes = by_sido.get(sido, {}).get(sgg)
        if not votes:
            unmatched += 1
            continue
        matched += 1
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
        r["valid_votes"] = votes["valid"]; r["invalid_votes"] = votes["invalid"]
        r["abstain"] = votes["abstain"]
        r.pop("votes_pending", None)
        r["candidates"].sort(key=lambda c: -(c.get("votes") or 0))
        for i, c in enumerate(r["candidates"]):
            c["rank"] = i + 1

    after = sum(1 for r in rows
                if any(c.get("party") and (c.get("votes") or 0) > 0 for c in (r.get("candidates") or [])))
    print(f"  {fid} ({path.name}) 기초비례 {len(rows)}곳: "
          f"득표 {before} → {after} · 남은 결손 {unmatched}{' [dry]' if dry else ''}")
    if not dry and matched:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="*", default=sorted(ELECTIONS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for n in args.n:
        if n not in ELECTIONS:
            print(f"  ! {n}회는 대상이 아니다"); continue
        backfill(n, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
