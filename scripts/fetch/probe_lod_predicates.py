"""제주 14대 총선 선거구 ElectionDistrict 노드의 모든 predicate·값을 덤프.

목적: LOD가 electorCount·validityVoteCount 외에 투표수(총)·무효표·기권 predicate도
주는지 확인. 주면 제주(VCCP에 없음) 포함 전 선거구를 정확히 채울 수 있다.

사용:
  NEC_LOD_COOKIE='WMONID=...; SESSION_DATA_1=...' \
    python scripts/fetch/probe_lod_predicates.py [--uri Elec_219920324] [--filter 제주]
국내 IP + 브라우저 세션 쿠키 필요(fetch_lod_assembly.py와 동일).
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

ENDPOINT = "http://data.nec.go.kr/sparql/"
RS = "{http://www.w3.org/2001/sw/DataAccess/tests/result-set#}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"

QTMPL = """PREFIX neco: <http://data.nec.go.kr/ontology/>
SELECT DISTINCT ?dname ?p ?o WHERE {{
  <http://data.nec.go.kr/resource/{uri}> neco:hasCandidate ?c .
  ?c neco:hasElectionDistrict ?d .
  ?d neco:name ?dname . FILTER(lang(?dname)="")
  FILTER(CONTAINS(?dname, "{flt}"))
  ?d ?p ?o .
}} ORDER BY ?dname ?p LIMIT 200"""


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default="Elec_219920324")
    ap.add_argument("--filter", default="제주")
    args = ap.parse_args()
    cookie = os.environ.get("NEC_LOD_COOKIE")
    if not cookie:
        sys.exit("NEC_LOD_COOKIE 환경변수 필요 (브라우저에서 복사)")
    rows = parse_rows(run(QTMPL.format(uri=args.uri, flt=args.filter), cookie))
    by_d = defaultdict(list)
    for r in rows:
        p = (r.get("p") or "").replace("http://data.nec.go.kr/ontology/", "neco:")
        by_d[r.get("dname")].append((p, r.get("o")))
    for d in sorted(by_d):
        print(f"\n=== {d} ===")
        for p, o in by_d[d]:
            ov = (o or "").replace("http://data.nec.go.kr/ontology/", "neco:").replace("http://data.nec.go.kr/resource/", "")
            print(f"  {p:42} {ov}")


if __name__ == "__main__":
    main()
