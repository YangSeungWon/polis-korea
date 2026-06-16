"""info.nec.go.kr VCCP09(electionType=2, electionCode=2) → 옛 총선 선거구별 투표수·무효표 보강.

14·15·16대 총선은 LOD에서 선거구 선거인수·유효득표는 받았지만 투표수(voters)·무효표가 없어
전국·지역 투표율이 안 나왔다. VCCP09 개표(시도 1쿼리, 선거구 3행 블록: 선거구명 / 선거인수·
투표수·무효 / 득표율)에서 선거구별 투표수·무효를 받아 지역구 race에 채운다.
→ 투표율 = 투표수/선거인수 (무효 포함), 지역별 투표율도 확보.

사용: python scripts/fetch/fetch_general_turnout.py [--n 14,15,16] [--dry-run]
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
ELECTIONS = {14: ("14th-general-1992", "19920324"),
             15: ("15th-general-1996", "19960411"),
             16: ("16th-general-2000", "20000413")}
CITYCODE = {
    "서울": "1100", "부산": "2600", "대구": "2700", "인천": "2800", "광주": "2900",
    "대전": "3000", "울산": "3100", "경기": "4100", "강원": "4200", "충청북": "4300",
    "충청남": "4400", "전라북": "4500", "전라남": "4600", "경상북": "4700", "경상남": "4800", "제주": "5000",
}


def sido_core(name: str) -> str:
    for suf in ("특별자치도", "특별자치시", "특별시", "광역시", "직할시", "도"):
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


def norm_dist(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


def num(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def fetch_sido(election_name: str, city_code: str) -> dict:
    """{norm 선거구명: (선거인수, 투표수, 무효)}."""
    data = urllib.parse.urlencode({
        "electionId": "0000000000", "requestURI": "/electioninfo/0000000000/vc/vccp09.jsp",
        "topMenuId": "VC", "secondMenuId": "VCCP09", "menuId": "VCCP09", "statementId": "VCCP09_#2",
        "oldElectionType": "1", "electionType": "2", "electionName": election_name, "electionCode": "2",
        "cityCode": city_code, "townCode": "-1", "sggCityCode": "-1"}).encode()
    req = urllib.request.Request(VCCP_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    tables = pd.read_html(StringIO(html))
    leaf = lambda c: (c[-1] if isinstance(c, tuple) else c)
    t = None
    for x in tables:
        leaves = [str(leaf(c)) for c in x.columns]
        if "선거구명" in leaves and "선거인수" in leaves:
            t = x; break
    if t is None or len(t) < 2:
        return {}
    cols = list(t.columns)
    c_dist, c_el, c_vt, c_inv = cols[0], cols[2], cols[3], cols[-2]
    out = {}
    i = 0
    while i + 1 < len(t):
        name = t.iloc[i][c_dist]
        meta = t.iloc[i + 1]
        if isinstance(name, str) and name.strip() and "조회된 자료" not in name:
            el, vt, inv = num(meta[c_el]), num(meta[c_vt]), num(meta[c_inv])
            if vt:
                out[norm_dist(name)] = (el, vt, inv or 0)
            i += 3
        else:
            i += 1
    return out


def backfill(n, dry):
    fid, en = ELECTIONS[n]
    path = RESULTS / f"{fid}.json"
    data = json.loads(path.read_text())
    dist = [r for r in data.get("races", []) if r.get("scope") == "district"]
    # sido_core → 그 시도 선거구 race들
    by_core = {}
    for r in dist:
        by_core.setdefault(sido_core(r.get("sido", "")), {})[norm_dist(r.get("district", ""))] = r

    matched = unmatched = 0
    tot_v = tot_e = 0
    for core, cc in CITYCODE.items():
        if core not in by_core:
            continue
        try:
            vc = fetch_sido(en, cc)
        except Exception as e:
            print(f"  ! {core} 실패: {e}"); continue
        for dname, (el, vt, inv) in vc.items():
            race = by_core[core].get(dname)
            if not race:
                unmatched += 1
                continue
            matched += 1
            race["voters"] = vt
            race["invalid_votes"] = inv
            if el:
                race["electors"] = el
            tot_v += vt; tot_e += el or race.get("electors") or 0
    to = 100 * tot_v / tot_e if tot_e else 0
    print(f"  {fid}: 매칭 {matched} · 미매칭 {unmatched} | 투표율 {to:.1f}%{' [dry]' if dry else ''}")
    if not dry and matched:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="14,15,16")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for n in [int(x) for x in args.n.split(",")]:
        backfill(n, args.dry_run)


if __name__ == "__main__":
    main()
