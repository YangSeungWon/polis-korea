"""data.go.kr 무투표선거구 당선인 API → results/local_N.json patch.

raw xlsx에 row 없는 무투표 당선 시군구를 API에서 가져와 results JSON에 추가.

사용:
  NEC_API_KEY=... .venv/bin/python scripts/fetch_uncontested.py [n=5,6,7,8]

API: https://apis.data.go.kr/9760000/WtvtelpcInfoInqireService/getWtvtelpcsccnInfoInqire
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data/results"
API_URL = "https://apis.data.go.kr/9760000/WtvtelpcInfoInqireService/getWtvtelpcsccnInfoInqire"

SG_ID = {  # 지선 회차 → 선거일
    5: "20100602",
    6: "20140604",
    7: "20180613",
    8: "20220601",
}
SG_TYPECODE = {  # 우리 office → API code
    "광역단체장": "3",  # 시도지사
    "기초단체장": "4",  # 구시군의장
    "교육감":     "5",
}


def fetch_uncontested(key: str, sg_id: str, sg_typecode: str) -> list[dict]:
    """무투표선거구 당선자 list 반환."""
    url = f"{API_URL}?serviceKey={key}&sgId={sg_id}&sgTypecode={sg_typecode}&pageNo=1&numOfRows=200"
    r = urllib.request.urlopen(url, timeout=30)
    root = ET.fromstring(r.read())
    code = root.findtext("header/resultCode")
    if code != "INFO-00":
        print(f"  ! API error: code={code} msg={root.findtext('header/resultMsg')}", file=sys.stderr)
        return []
    out = []
    for it in root.findall("body/items/item"):
        out.append({
            "sido":   it.findtext("sdName") or "",
            "sigungu": it.findtext("sggName") or "",
            "party":  it.findtext("jdName") or "무소속",
            "name":   it.findtext("name") or "",
        })
    return out


def patch_local_json(n: int, office: str, uncontested: list[dict]) -> int:
    """results/local_{n}.json의 office에 무투표 당선자 추가. 반환=patched 수."""
    path = RESULTS / f"local_{n}.json"
    if not path.exists():
        print(f"  ! {path.name} 없음", file=sys.stderr)
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    office_data = data.get("offices", {}).get(office)
    if not office_data:
        print(f"  ! {n}회 {office} office 없음", file=sys.stderr)
        return 0
    sigungu_list = office_data.setdefault("sigungu", [])
    existing = {(s["sido"], s["name"]) for s in sigungu_list}
    added = 0
    for u in uncontested:
        key = (u["sido"], u["sigungu"])
        if key in existing:
            continue
        sigungu_list.append({
            "sido": u["sido"],
            "name": u["sigungu"],
            "electors": 0,
            "voted": 0,
            "turnout": 0.0,
            "uncontested": True,
            "candidates": [{
                "name": u["name"],
                "party": u["party"],
                "votes": 0,
                "pct": 100.0,
            }],
        })
        added += 1
    if added:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=str, default="5,6,7,8")
    args = ap.parse_args()
    key = os.environ.get("NEC_API_KEY")
    if not key:
        print("ERR: NEC_API_KEY 환경변수 설정 필요", file=sys.stderr)
        sys.exit(1)
    rounds = [int(x) for x in args.rounds.split(",")]
    for n in rounds:
        sg_id = SG_ID.get(n)
        if not sg_id:
            print(f"  skip n={n} (sgId 매핑 없음)", file=sys.stderr)
            continue
        print(f"=== {n}회 (sgId={sg_id}) ===", file=sys.stderr)
        for office, code in SG_TYPECODE.items():
            uncontested = fetch_uncontested(key, sg_id, code)
            if not uncontested:
                print(f"  {office}: 무투표 0", file=sys.stderr)
                continue
            added = patch_local_json(n, office, uncontested)
            print(f"  {office}: 무투표 {len(uncontested)}명 발견, {added} patched", file=sys.stderr)


if __name__ == "__main__":
    main()
