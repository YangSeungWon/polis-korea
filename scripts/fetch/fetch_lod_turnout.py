"""NEC LOD → 14·15·16대 총선 선거구별 총투표수·무효표·선거인수 보강(투표율).

fetch_lod_assembly가 electorCount·validityVoteCount만 받아 투표수(voters)·무효가 없었다.
같은 ElectionDistrict 노드에 neco:voteCount(총투표수)·neco:unavailableVoteCount(무효)가
있어, 이를 받아 지역구 race에 voters/invalid_votes로 채운다. VCCP(제주 옛회차 결측)와 달리
LOD는 제주 포함 전 선거구를 권위 단일 소스로 제공 → 투표율 정확.

검산: voteCount = validityVoteCount + unavailableVoteCount, electorCount = voteCount + abstention.

사용:
  NEC_LOD_COOKIE='WMONID=...; SESSION_DATA_1=...' \
    python scripts/fetch/fetch_lod_turnout.py [--n 14,15,16] [--dry-run]
국내 IP + 브라우저 세션 쿠키 필요(fetch_lod_assembly.py와 동일).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
ENDPOINT = "http://data.nec.go.kr/sparql/"
RS = "{http://www.w3.org/2001/sw/DataAccess/tests/result-set#}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"

ELECTIONS = {
    14: ("14th-general-1992", "Elec_219920324"),
    15: ("15th-general-1996", "Elec_219960411"),
    16: ("16th-general-2000", "Elec_220000413"),
}

QTMPL = """PREFIX neco: <http://data.nec.go.kr/ontology/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT DISTINCT ?dname ?sido ?electors ?votes ?invalid WHERE {{
  ?d neco:relationElection <http://data.nec.go.kr/resource/{uri}> .
  ?d rdf:type neco:ElectionDistrict .
  ?d neco:name ?dname . FILTER(lang(?dname)="")
  OPTIONAL {{ ?d neco:electorCount ?electors }}
  OPTIONAL {{ ?d neco:voteCount ?votes }}
  OPTIONAL {{ ?d neco:unavailableVoteCount ?invalid }}
  OPTIONAL {{ ?d neco:cityAndProvinces ?cp . ?cp neco:name ?sido . FILTER(lang(?sido)="") }}
}} ORDER BY ?dname LIMIT 100 OFFSET {off}"""


def run(query: str, cookie: str):
    out = subprocess.run([
        "curl", "-s", "--compressed", "-G", ENDPOINT,
        "-H", f"Cookie: {cookie}", "-H", "User-Agent: Mozilla/5.0",
        "--data", "request_method=get", "--data-urlencode", f"query={query}",
        "--max-time", "90",
    ], capture_output=True, timeout=100)
    if not out.stdout:
        sys.exit(f"빈 응답 (쿠키/IP 확인). stderr: {out.stderr.decode()[:200]}")
    return ET.fromstring(out.stdout)


def parse_rows(root):
    binds, sols = {}, []
    for d in root.findall(RDF + "Description"):
        nid = d.get(RDF + "nodeID")
        var, val = d.find(RS + "variable"), d.find(RS + "value")
        if var is not None:
            v = (val.get(RDF + "resource") if (val is not None and val.get(RDF + "resource"))
                 else (val.text if val is not None else None))
            binds[nid] = (var.text, v)
        elif d.find(RS + "binding") is not None:
            sols.append([b.get(RDF + "nodeID") for b in d.findall(RS + "binding")])
    rows = []
    for s in sols:
        r = {}
        for nid in s:
            if nid in binds:
                k, v = binds[nid]
                r[k] = v
        rows.append(r)
    return rows


# 데이터는 전북특별자치도(core 전북), LOD는 전라북도(core 전라북) — 별칭으로 흡수.
CORE_ALIAS = {"전라북": "전북", "전라남": "전남", "충청북": "충북", "충청남": "충남",
              "경상북": "경북", "경상남": "경남"}


def sido_core(name: str) -> str:
    for suf in ("특별자치도", "특별자치시", "특별시", "광역시", "직할시", "도"):
        if name and name.endswith(suf):
            core = name[: -len(suf)]
            return CORE_ALIAS.get(core, core)
    return CORE_ALIAS.get(name, name) if name else ""


def norm(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


def to_int(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def fetch_districts(uri: str, cookie: str) -> list[dict]:
    out, off = [], 0
    while True:
        rows = parse_rows(run(QTMPL.format(uri=uri, off=off), cookie))
        out.extend(rows)
        if len(rows) < 100:
            break
        off += 100
        time.sleep(0.3)
    return out


def backfill(n, cookie, dry):
    fid, uri = ELECTIONS[n]
    path = RESULTS / f"{fid}.json"
    data = json.loads(path.read_text())
    dist = [r for r in data.get("races", []) if r.get("scope") == "district"]
    by_key = {}
    for r in dist:
        by_key[(sido_core(r.get("sido", "")), norm(r.get("district", "")))] = r

    rows = fetch_districts(uri, cookie)
    matched = miss = bad = 0
    tot_v = tot_e = 0
    for row in rows:
        key = (sido_core(row.get("sido", "")), norm(row.get("dname", "")))
        race = by_key.get(key)
        if not race:
            miss += 1
            continue
        votes, inv, el = to_int(row.get("votes")), to_int(row.get("invalid")), to_int(row.get("electors"))
        if votes is None:
            bad += 1
            continue
        # 검산: 유효+무효 = 총투표 (데이터 valid_votes 있으면)
        vv = race.get("valid_votes")
        if vv is not None and inv is not None and vv + inv != votes:
            bad += 1
            print(f"  ! 검산불일치 {key}: valid{vv}+inv{inv}≠vote{votes}")
        race["voters"] = votes
        if inv is not None:
            race["invalid_votes"] = inv
        if el:
            race["electors"] = el
        matched += 1
        tot_v += votes
        tot_e += el or race.get("electors") or 0
    to = 100 * tot_v / tot_e if tot_e else 0
    print(f"  {fid}: 매칭 {matched} · LOD미매칭 {miss} · 결측/불일치 {bad} | 투표율 {to:.2f}%{' [dry]' if dry else ''}")
    if not dry and matched:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="14,15,16")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cookie = os.environ.get("NEC_LOD_COOKIE")
    if not cookie:
        sys.exit("NEC_LOD_COOKIE 환경변수 필요 (브라우저에서 복사)")
    for n in [int(x) for x in args.n.split(",")]:
        backfill(n, cookie, args.dry_run)


if __name__ == "__main__":
    main()
