"""data.go.kr 투·개표 정보 API → 5~8회 지선 광역·기초·교육감 후보별 + turnout 완전 백필.

sgTypecode:
  3 = 광역단체장 (시도지사)
  4 = 기초단체장 (구시군의장)
 11 = 교육감

응답은 sggName 단위. wiwName='합계' row = 그 sgg 전체 합계.
- 광역(3): sgg = 시도명. 시도별 1개 row.
- 기초(4): sgg = 시군구명. 시군구별 1개 row.
- 교육감(11): sgg = 시도명. 시도별 1개 row (정당 없음).

산출: results/local_{n}.json offices[광역/기초/교육감].sigungu[] 백필.

사용: NEC_API_KEY=... .venv/bin/python scripts/fetch_local_full.py [--rounds 5,6,7,8]
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

ROOT = Path(__file__).resolve().parent.parent
API = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire"

SG_ID = {5: "20100602", 6: "20140604", 7: "20180613", 8: "20220601"}
OFFICE_CODE = {"광역단체장": 3, "기초단체장": 4, "교육감": 11}

SIDO_API_NAME_BY_ROUND = {
    5: {"강원특별자치도": "강원도", "전북특별자치도": "전라북도", "제주특별자치도": "제주특별자치도"},
    6: {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"},
    7: {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"},
    8: {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"},
}

ALL_SIDO = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
    "울산광역시", "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도",
    "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도",
]


def to_int(s):
    if not s: return 0
    try: return int(str(s).replace(",", "").strip() or 0)
    except: return 0


def parse_item(item, has_party: bool = True) -> dict:
    """API response item → {electors, voted, turnout, candidates: [...]}"""
    electors = to_int(item.findtext("sunsu"))
    voted = to_int(item.findtext("tusu"))
    valid = to_int(item.findtext("yutusu"))
    cands = []
    for i in range(1, 51):
        name = item.findtext(f"hbj{i:02d}")
        party = item.findtext(f"jd{i:02d}") if has_party else "교육감"
        votes = to_int(item.findtext(f"dugsu{i:02d}"))
        if not name and not party: continue
        if not name and votes == 0: continue
        cands.append({
            "name": (name or "").strip(),
            "party": (party or "무소속").strip(),
            "votes": votes,
            "pct": round(votes / valid * 100, 2) if valid > 0 else 0.0,
        })
    cands.sort(key=lambda c: -c["votes"])
    return {
        "electors": electors,
        "voted": voted,
        "turnout": round(voted / electors * 100, 2) if electors > 0 else 0.0,
        "candidates": cands,
    }


def fetch(key: str, sg_id: str, sg_typecode: int, sido: str,
          sgg_name: str = "") -> list[ET.Element]:
    """페이지 loop fetch — 한 시도의 모든 row."""
    items = []
    page = 1
    while True:
        sd_enc = urllib.parse.quote(sido)
        sg_enc = urllib.parse.quote(sgg_name) if sgg_name else ""
        url = (f"{API}?serviceKey={key}&sgId={sg_id}&sgTypecode={sg_typecode}"
               f"&sdName={sd_enc}&pageNo={page}&numOfRows=200")
        if sgg_name:
            url += f"&sggName={sg_enc}"
        try:
            r = urllib.request.urlopen(url, timeout=30)
        except urllib.error.HTTPError:
            return items
        root = ET.fromstring(r.read())
        if root.findtext("header/resultCode") != "INFO-00":
            return items
        cur = root.findall("body/items/item")
        if not cur: break
        items.extend(cur)
        total = int(root.findtext("body/totalCount") or 0)
        if page * 200 >= total: break
        page += 1
    return items


def fetch_office(key: str, sg_id: str, office: str, api_sido_map: dict) -> dict:
    """한 office 모든 시도 fetch → {(sido, sgg): {electors, voted, turnout, candidates}}"""
    code = OFFICE_CODE[office]
    has_party = (office != "교육감")
    out = {}
    for sido in ALL_SIDO:
        api_sido = api_sido_map.get(sido, sido)
        items = fetch(key, sg_id, code, api_sido)
        # wiwName='합계' 추출
        for it in items:
            if it.findtext("wiwName") != "합계": continue
            sgg = (it.findtext("sggName") or "").strip()
            if not sgg: continue
            parsed = parse_item(it, has_party=has_party)
            # 광역·교육감: sgg = 시도명. 기초: sgg = 시군구명.
            out[(sido, sgg)] = parsed
        time.sleep(0.02)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=str, default="5,6,7,8")
    ap.add_argument("--offices", type=str, default="광역단체장,기초단체장,교육감")
    args = ap.parse_args()
    key = os.environ.get("NEC_API_KEY")
    if not key:
        print("ERR: NEC_API_KEY 필요", file=sys.stderr); sys.exit(1)
    rounds = [int(x) for x in args.rounds.split(",")]
    offices = args.offices.split(",")

    for n in rounds:
        sg_id = SG_ID.get(n)
        if not sg_id: continue
        api_map = SIDO_API_NAME_BY_ROUND.get(n, {})
        rp = ROOT / f"data/results/local_{n}.json"
        if not rp.exists():
            print(f"  ! {rp.name} 없음", file=sys.stderr); continue
        data = json.loads(rp.read_text(encoding="utf-8"))
        for office in offices:
            print(f"=== {n}회 {office} ===", file=sys.stderr)
            results = fetch_office(key, sg_id, office, api_map)
            print(f"  fetched {len(results)} rows", file=sys.stderr)
            # offices[office].sigungu에 반영
            ofd = data.setdefault("offices", {}).setdefault(office, {})
            existing = {(s["sido"], s["name"]): s for s in ofd.get("sigungu", [])}
            for (sido, sgg), res in results.items():
                rec = existing.get((sido, sgg))
                if rec is None:
                    rec = {"sido": sido, "name": sgg}
                    ofd.setdefault("sigungu", []).append(rec)
                    existing[(sido, sgg)] = rec
                rec.update(res)
            # national 합산
            nat = {"electors": 0, "voted": 0}
            for res in results.values():
                nat["electors"] += res["electors"]; nat["voted"] += res["voted"]
            if nat["electors"]:
                nat["turnout"] = round(nat["voted"] / nat["electors"] * 100, 2)
                ofd["national"] = ofd.get("national") or {}
                ofd["national"].update(nat)
        rp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → {rp.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
