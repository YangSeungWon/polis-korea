"""data.go.kr 당선인 정보 API → 17·18대 총선 지역구 결과 백필.

API:
  https://apis.data.go.kr/9760000/WinnerInfoInqireService2/getWinnerInfoInqire
  sgTypecode=2 (국회의원), sdName loop.

산출:
  data/geo/district_{n}_centroid.json    — 지역구 list (build_district_hex_v2 입력)
  data/results/national_assembly_{n}.json — district[] 필드 patch (winner_party 등)

사용:
  NEC_API_KEY=... .venv/bin/python scripts/fetch_districts_api.py [--rounds 17,18]
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
API_URL = "https://apis.data.go.kr/9760000/WinnerInfoInqireService2/getWinnerInfoInqire"

ELECTION_DATES = {
    17: ("20040415", "2004-04-15"),
    18: ("20080409", "2008-04-09"),
    19: ("20120411", "2012-04-11"),
    20: ("20160413", "2016-04-13"),
    21: ("20200415", "2020-04-15"),
    22: ("20240410", "2024-04-10"),
}

SIDOS = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "강원도",  # 옛 이름 fallback (17·18대)
    "충청북도", "충청남도", "전북특별자치도", "전라북도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
    "제주도",  # 17대 (2006 특별자치도 승격 전)
]

# fetched sido name → 현행 캐노니컬 (results JSON 통일 위함)
SIDO_CANON = {
    "강원도":         "강원특별자치도",
    "전라북도":       "전북특별자치도",
    "제주도":         "제주특별자치도",
}


def fetch_sido(key: str, sg_id: str, sido: str, sg_typecode: int = 2) -> list[dict]:
    """한 시도의 국회의원 당선자 list. sgTypecode=2 지역구, =7 비례대표."""
    out = []
    page = 1
    while True:
        sd_enc = urllib.parse.quote(sido)
        url = f"{API_URL}?serviceKey={key}&sgId={sg_id}&sgTypecode={sg_typecode}&sdName={sd_enc}&pageNo={page}&numOfRows=100"
        try:
            r = urllib.request.urlopen(url, timeout=30)
        except urllib.error.HTTPError as e:
            print(f"  ! {sido}: HTTP {e.code}", file=sys.stderr)
            return out
        root = ET.fromstring(r.read())
        code = root.findtext("header/resultCode")
        if code != "INFO-00":
            return out
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            sd_raw = it.findtext("sdName") or ""
            out.append({
                "sido":     SIDO_CANON.get(sd_raw, sd_raw),
                "name":     it.findtext("sggName") or "",  # 지역구명 (예: 성동구갑)
                "wiw":      it.findtext("wiwName") or "",  # 시군구 (예: 성동구)
                "winner":   it.findtext("name") or "",
                "winner_party": it.findtext("jdName") or "",
                "votes":    int(it.findtext("dugsu") or 0),
                "pct":      float(it.findtext("dugyul") or 0),
            })
        total = int(root.findtext("body/totalCount") or 0)
        if page * 100 >= total:
            break
        page += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=str, default="17,18")
    args = ap.parse_args()
    key = os.environ.get("NEC_API_KEY")
    if not key:
        print("ERR: NEC_API_KEY 환경변수 필요", file=sys.stderr); sys.exit(1)

    for n in [int(x) for x in args.rounds.split(",")]:
        sg_id, date = ELECTION_DATES.get(n, (None, None))
        if not sg_id:
            print(f"  skip n={n}", file=sys.stderr); continue
        print(f"=== {n}대 총선 ({date}) ===", file=sys.stderr)
        all_districts = []
        for sido in SIDOS:
            rows = fetch_sido(key, sg_id, sido)
            if rows:
                all_districts.extend(rows)
                print(f"  {sido}: {len(rows)}", file=sys.stderr)
        # 중복 제거 (sido + name)
        seen = set()
        uniq = []
        for d in all_districts:
            key2 = (d["sido"], d["name"])
            if key2 in seen: continue
            seen.add(key2)
            uniq.append(d)
        print(f"  총 지역구: {len(uniq)}", file=sys.stderr)

        # 1. district_{n}_centroid.json — build_district_hex_v2 입력
        centroid_list = [{"sido": d["sido"], "name": d["name"]} for d in uniq]
        cp = ROOT / f"data/geo/district_{n}_centroid.json"
        cp.write_text(json.dumps(centroid_list, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → {cp.relative_to(ROOT)}", file=sys.stderr)

        # 2. results/national_assembly_{n}.json — district[] patch
        rp = ROOT / f"data/results/national_assembly_{n}.json"
        data = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {
            "_meta": {"type": "national_assembly", "n": n, "date": date,
                      "label": f"{n}대 국회의원선거", "source": "data.go.kr NEC 당선인 정보 API"},
            "national": {"candidates": [], "turnout": None, "proportional_seats": []},
            "sigungu": [],
        }
        data["district"] = [{
            "sido": d["sido"],
            "name": d["name"],
            "winner": d["winner"],
            "winner_party": d["winner_party"],
            "candidates": [{"name": d["winner"], "party": d["winner_party"],
                            "votes": d["votes"], "pct": d["pct"]}],
        } for d in uniq]
        rp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → {rp.relative_to(ROOT)} (district {len(uniq)})", file=sys.stderr)


if __name__ == "__main__":
    main()
