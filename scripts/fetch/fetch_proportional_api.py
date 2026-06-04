"""data.go.kr 당선인 정보 API → 비례대표 의석 백필.

sgTypecode=7 (국회의원 비례대표), sdName='전국'으로 fetch.
각 당선자의 정당 카운트 → 정당별 의석 수.

산출: results/national_assembly_{n}.json의 national.proportional_seats 업데이트.

사용:
  NEC_API_KEY=... .venv/bin/python scripts/fetch/fetch_proportional_api.py [--rounds 17,18,19,20,21,22]
"""
from __future__ import annotations
import argparse
import collections
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_URL = "https://apis.data.go.kr/9760000/WinnerInfoInqireService2/getWinnerInfoInqire"

ELECTION_DATES = {
    17: "20040415",
    18: "20080409",
    19: "20120411",
    20: "20160413",
    21: "20200415",
    22: "20240410",
}


def fetch_proportional(key: str, sg_id: str) -> dict[str, int]:
    """비례 당선자 → 정당별 의석 카운트."""
    counts = collections.Counter()
    for sd in ("전국", ""):
        page = 1
        while True:
            sd_enc = urllib.parse.quote(sd)
            url = (f"{API_URL}?serviceKey={key}&sgId={sg_id}&sgTypecode=7"
                   f"&sdName={sd_enc}&pageNo={page}&numOfRows=100")
            try:
                r = urllib.request.urlopen(url, timeout=30)
            except urllib.error.HTTPError:
                break
            root = ET.fromstring(r.read())
            if root.findtext("header/resultCode") != "INFO-00":
                break
            items = root.findall("body/items/item")
            if not items:
                break
            for it in items:
                party = it.findtext("jdName") or "무소속"
                counts[party] += 1
            total = int(root.findtext("body/totalCount") or 0)
            if page * 100 >= total:
                break
            page += 1
        if counts:
            break  # 첫 sd로 데이터 가져왔으면 다른 시도 안 함
    return dict(counts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=str, default="17,18,19,20,21,22")
    args = ap.parse_args()
    key = os.environ.get("NEC_API_KEY")
    if not key:
        print("ERR: NEC_API_KEY 환경변수 필요", file=sys.stderr); sys.exit(1)

    for n in [int(x) for x in args.rounds.split(",")]:
        sg_id = ELECTION_DATES.get(n)
        if not sg_id:
            print(f"  skip n={n}", file=sys.stderr); continue
        counts = fetch_proportional(key, sg_id)
        if not counts:
            print(f"  {n}대 비례: 결과 없음", file=sys.stderr); continue
        total = sum(counts.values())
        print(f"=== {n}대 비례 (총 {total}석) ===", file=sys.stderr)
        for p, s in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {p}: {s}", file=sys.stderr)
        # results JSON에 patch
        rp = ROOT / f"data/results/national_assembly_{n}.json"
        if not rp.exists():
            print(f"  ! {rp.name} 없음", file=sys.stderr); continue
        data = json.loads(rp.read_text(encoding="utf-8"))
        prop_list = [{"party": p, "seats": s}
                     for p, s in sorted(counts.items(), key=lambda x: -x[1])]
        data.setdefault("national", {})["proportional_seats"] = prop_list
        rp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → {rp.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
