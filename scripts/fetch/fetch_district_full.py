"""data.go.kr 투·개표 정보 API → 17·18대 총선 지역구 후보별 + turnout 완전 백필.

API: VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire
응답 필드: sunsu (선거인수), tusu (투표수), yutusu (유효), mutusu (무효), gigwonsu (기권),
          jdN (정당명, 1~50), hbjN (후보자명), dugsuN (득표수)

각 지역구별 호출 → results JSON district[]의 candidates·electors·voted·turnout patch.

사용:
  NEC_API_KEY=... .venv/bin/python scripts/fetch/fetch_district_full.py [--rounds 17,18]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_URL = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire"

ELECTION_DATES = {
    17: "20040415", 18: "20080409", 19: "20120411",
    20: "20160413", 21: "20200415", 22: "20240410",
}

# 데이터의 옛 시도명 회차별 (API 호출 시)
SIDO_API_NAME_BY_ROUND = {
    17: {"강원특별자치도": "강원도", "전북특별자치도": "전라북도", "제주특별자치도": "제주도"},
    18: {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"},
    19: {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"},
    20: {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"},
    21: {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"},
    22: {"강원특별자치도": "강원도"},  # 22대 시점 전북은 이미 특별자치도 (2024.1)
}


def fetch_district(key: str, sg_id: str, sido: str, sgg_name: str) -> dict | None:
    """한 지역구의 개표결과 fetch → {electors, voted, candidates: [...]}"""
    sd_enc = urllib.parse.quote(sido)
    sg_enc = urllib.parse.quote(sgg_name)
    url = (f"{API_URL}?serviceKey={key}&sgId={sg_id}&sgTypecode=2"
           f"&sdName={sd_enc}&sggName={sg_enc}&pageNo=1&numOfRows=10")
    try:
        r = urllib.request.urlopen(url, timeout=30)
    except urllib.error.HTTPError as e:
        return None
    root = ET.fromstring(r.read())
    if root.findtext("header/resultCode") != "INFO-00":
        return None
    # items에서 wiwName='합계' row 사용 (또는 첫 row)
    item = None
    for it in root.findall("body/items/item"):
        if it.findtext("wiwName") == "합계":
            item = it; break
    if item is None:
        items = root.findall("body/items/item")
        item = items[0] if items else None
    if item is None: return None

    def to_int(s):
        if not s: return 0
        return int(str(s).replace(",", "").strip() or 0)

    electors = to_int(item.findtext("sunsu"))
    voted = to_int(item.findtext("tusu"))
    valid = to_int(item.findtext("yutusu"))
    # 정당·후보·득표
    cands = []
    for i in range(1, 51):
        party = item.findtext(f"jd{i:02d}")
        name = item.findtext(f"hbj{i:02d}")
        votes = to_int(item.findtext(f"dugsu{i:02d}"))
        if not party and not name:
            continue
        if votes == 0 and not party and not name:
            continue
        cands.append({
            "name": (name or "").strip(),
            "party": (party or "무소속").strip(),
            "votes": votes,
            "pct": round(votes / valid * 100, 2) if valid > 0 else 0.0,
        })
    # votes desc 정렬
    cands.sort(key=lambda c: -c["votes"])
    return {
        "electors": electors,
        "voted": voted,
        "turnout": round(voted / electors * 100, 2) if electors > 0 else 0.0,
        "candidates": cands,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=str, default="17,18")
    ap.add_argument("--delay", type=float, default=0.05)
    args = ap.parse_args()
    key = os.environ.get("NEC_API_KEY")
    if not key:
        print("ERR: NEC_API_KEY 환경변수 필요", file=sys.stderr); sys.exit(1)

    for n in [int(x) for x in args.rounds.split(",")]:
        sg_id = ELECTION_DATES.get(n)
        if not sg_id:
            print(f"  skip n={n}", file=sys.stderr); continue
        cp = ROOT / f"data/geo/district_{n}_centroid.json"
        rp = ROOT / f"data/results/national_assembly_{n}.json"
        if not cp.exists() or not rp.exists():
            print(f"  ! {n}대 centroid/results 없음", file=sys.stderr); continue
        centroids = json.loads(cp.read_text(encoding="utf-8"))
        data = json.loads(rp.read_text(encoding="utf-8"))

        # existing district[] index by (sido, name)
        existing = {(d["sido"], d["name"]): d for d in data.get("district", [])}

        sido_api_name = SIDO_API_NAME_BY_ROUND.get(n, {})

        ok = 0
        fail = []
        nat_electors = nat_voted = 0
        print(f"=== {n}대 (sgId={sg_id}, {len(centroids)} districts) ===", file=sys.stderr)
        for c in centroids:
            sido = c["sido"]; name = c["name"]
            api_sido = sido_api_name.get(sido, sido)
            res = fetch_district(key, sg_id, api_sido, name)
            if not res:
                fail.append((sido, name)); continue
            target = existing.get((sido, name))
            if target:
                target["electors"] = res["electors"]
                target["voted"] = res["voted"]
                target["turnout"] = res["turnout"]
                target["candidates"] = res["candidates"]
                if res["candidates"]:
                    target["winner"] = res["candidates"][0]["name"]
                    target["winner_party"] = res["candidates"][0]["party"]
            else:
                data.setdefault("district", []).append({
                    "sido": sido, "name": name,
                    "winner": res["candidates"][0]["name"] if res["candidates"] else "",
                    "winner_party": res["candidates"][0]["party"] if res["candidates"] else "",
                    **res,
                })
            nat_electors += res["electors"]; nat_voted += res["voted"]
            ok += 1
            if args.delay: time.sleep(args.delay)
        print(f"  성공 {ok}, 실패 {len(fail)}", file=sys.stderr)
        for s, nm in fail[:10]: print(f"    ! {s} {nm}", file=sys.stderr)
        # national turnout 갱신
        data.setdefault("national", {})
        if nat_electors > 0:
            data["national"]["electors"] = nat_electors
            data["national"]["voted"] = nat_voted
            data["national"]["turnout"] = round(nat_voted / nat_electors * 100, 2)
        rp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → {rp.relative_to(ROOT)} (national turnout={data['national'].get('turnout')}%)", file=sys.stderr)


if __name__ == "__main__":
    main()
