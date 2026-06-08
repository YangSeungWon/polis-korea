"""NEC LOD(data.nec.go.kr SPARQL) → 14·15·16대 총선 지역구 race 재구성.

OpenAPI·다운로드가 17~19대에서 끊기는 옛 총선의 선거구별 후보·득표를 LOD에서 회수.
LOD 엔드포인트는 format 무시하고 SPARQL RDF/XML 결과셋만 주며, 결과 100행 캡 →
LIMIT 100 OFFSET 페이징. 국내 IP 전용 + 세션 쿠키 필요(브라우저에서 복사).

당선 = 선거구 내 최다 득표(소선거구 numberOfElection=1). 전국구(비례)는 별도 투표가
아니라 배분이라 LOD 지역구엔 없음 → 기존 nation total − 지역구 으로 도출.

사용:
  NEC_LOD_COOKIE='WMONID=...; SESSION_DATA_1=...' \
    python scripts/fetch/fetch_lod_assembly.py [--n 14,15,16] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
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

# 정당명 시대차 — LOD 지역구명 → 기존 nation total명(합산 정규화). 15대 통합민주당=민주당.
PARTY_ALIAS = {"통합민주당": "민주당"}

# LOD 시대명(직할시) → 우리 데이터 현행명.
SIDO_NORM = {
    "부산직할시": "부산광역시", "대구직할시": "대구광역시", "인천직할시": "인천광역시",
    "광주직할시": "광주광역시", "대전직할시": "대전광역시", "제주도": "제주특별자치도",
    "강원도": "강원특별자치도", "전라북도": "전북특별자치도",
}

QTMPL = """PREFIX neco: <http://data.nec.go.kr/ontology/>
SELECT ?sido ?dname ?seats ?electors ?valid ?cname ?pname ?symbol ?votes WHERE {{
  <http://data.nec.go.kr/resource/{uri}> neco:hasCandidate ?c .
  ?c neco:name ?cname . FILTER(lang(?cname)="")
  ?c neco:pollingScoreCount ?votes ; neco:electionSymbol ?symbol ;
     neco:positionPoliticalParty ?p ; neco:hasElectionDistrict ?d .
  ?p neco:name ?pname . FILTER(lang(?pname)="")
  ?d neco:name ?dname . FILTER(lang(?dname)="")
  OPTIONAL {{ ?d neco:numberOfElection ?seats }}
  OPTIONAL {{ ?d neco:electorCount ?electors }}
  OPTIONAL {{ ?d neco:validityVoteCount ?valid }}
  OPTIONAL {{ ?d neco:cityAndProvinces ?cp . ?cp neco:name ?sido . FILTER(lang(?sido)="") }}
}} ORDER BY ?dname ?cname LIMIT 100 OFFSET {off}"""


def run(query: str, cookie: str):
    # curl(검증됨)로 호출 — urllib은 동일 요청에 500 반환(인코딩 차이).
    out = subprocess.run([
        "curl", "-s", "--compressed", "-G", ENDPOINT,
        "-H", f"Cookie: {cookie}", "-H", "User-Agent: Mozilla/5.0",
        "--data", "request_method=get", "--data-urlencode", f"query={query}",
        "--max-time", "90",
    ], capture_output=True, timeout=100)
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


def fetch_all(uri: str, cookie: str):
    rows, off, seen = [], 0, set()
    while True:
        batch = parse_rows(run(QTMPL.format(uri=uri, off=off), cookie))
        for r in batch:
            key = (r.get("dname"), r.get("cname"), r.get("votes"))
            if key not in seen:
                seen.add(key)
                rows.append(r)
        if len(batch) < 100:
            break
        off += 100
        time.sleep(0.3)
    return rows


def build_races(rows):
    by = defaultdict(list)
    for r in rows:
        sido = SIDO_NORM.get(r.get("sido") or "", r.get("sido") or "")
        by[(sido, r.get("dname"))].append(r)
    races = []
    for (sido, dname), cs in sorted(by.items()):
        seats = int(cs[0].get("seats") or 1)
        valid = int(cs[0].get("valid") or 0)
        electors = int(cs[0].get("electors") or 0)
        cands = sorted(cs, key=lambda c: -int(c.get("votes") or 0))
        out = []
        for i, c in enumerate(cands):
            v = int(c.get("votes") or 0)
            party = PARTY_ALIAS.get(c.get("pname"), c.get("pname"))
            out.append({
                "name": c.get("cname"), "party": party,
                "votes": v, "pct": round(v / valid * 100, 2) if valid else None,
                "rank": i + 1, "won": i < seats,
            })
        races.append({
            "sg_typecode": "2", "scope": "district", "sido": sido, "sigungu": dname,
            "district": dname, "electors": electors, "valid_votes": valid,
            "seats_total": seats, "candidates": out,
        })
    return races


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="14,15,16")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cookie = os.environ.get("NEC_LOD_COOKIE", "")
    if not cookie:
        sys.exit("NEC_LOD_COOKIE 환경변수 필요 (브라우저 세션 쿠키)")
    for n in [int(x) for x in args.n.split(",")]:
        fid, uri = ELECTIONS[n]
        rows = fetch_all(uri, cookie)
        races = build_races(rows)
        # 검증: 정당별 지역구 의석
        seat = defaultdict(int)
        for r in races:
            for c in r["candidates"]:
                if c["won"]:
                    seat[c["party"]] += 1
        nwin = sum(seat.values())
        print(f"=== {fid}: 후보 {len(rows)} · 선거구 {len(races)} · 지역구 당선 {nwin} ===")
        for p, c in sorted(seat.items(), key=lambda x: -x[1])[:6]:
            print(f"    {p}: {c}")
        if args.dry_run:
            continue
        path = RESULTS / f"{fid}.json"
        data = json.loads(path.read_text())
        # 기존 district race 제거 후 새로 (14·15·16은 원래 없음) — nation race는 보존
        data["races"] = [r for r in data.get("races", []) if r.get("scope") != "district"] + races
        # 전국구(비례) 도출: nation total − 지역구 → proportional_seats
        nats = [r for r in data["races"] if r.get("scope") == "nation"]
        if nats:
            for c in nats[0].get("candidates", []):
                tot = c.get("seats")
                if isinstance(tot, int):
                    c["proportional_seats"] = max(0, tot - seat.get(c.get("party"), 0))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print(f"    → {path.name} 저장 (지역구 race {len(races)})")


if __name__ == "__main__":
    main()
