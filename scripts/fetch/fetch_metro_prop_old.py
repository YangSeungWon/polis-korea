"""data.go.kr 당선인 API → 광역의회 비례(sgTypecode=8) 의석 백필 (3·4회 2002·2006).

3·4회 지선 결과는 단체장·지역구의원만 수집돼 광역 비례(정당투표)가 비어 있었다.
2002년 3회는 한국 최초 정당명부 비례 직접투표(헌재 위헌결정 후 1인 2표제). NEC 당선인
명부(sgTypecode=8)에 2002·2006 데이터가 있어 시도·정당별 의석을 회수해 proportional_sido
race로 추가한다. 득표수는 이 API에 없어 votes_pending=True(의석만 확정) — 추후 개표 소스로 보강.

사용:
  NEC_API_KEY=... .venv/bin/python scripts/fetch/fetch_metro_prop_old.py [--dry-run] [--n 3]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
API = "https://apis.data.go.kr/9760000/WinnerInfoInqireService2/getWinnerInfoInqire"
# 회차 → (결과 파일 id, sgId 선거일)
ELECTIONS = {
    3: ("3rd-local-2002", "20020613"),
    4: ("4th-local-2006", "20060531"),
}


def load_key() -> str:
    key = os.environ.get("NEC_API_KEY")
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("NEC_API_KEY"):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not key:
        sys.exit("NEC_API_KEY 없음 (.env 또는 환경변수)")
    return key


def load_party_canon() -> dict:
    """정당 alias/약칭 → 정식명 (registry.json). 비례 API의 '자민련'을 '자유민주연합'으로 통일."""
    reg = json.loads((ROOT / "data" / "parties" / "registry.json").read_text()).get("parties", {})
    canon = {}
    for name, info in reg.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        canon[name] = name
        if info.get("abbr"):
            canon[info["abbr"]] = name
        for a in info.get("aliases", []):
            canon[a] = name
    return canon


def fetch_metro_prop(key: str, sg_id: str):
    """sgTypecode=8 광역 비례 당선인 → {sido: {party: seats}}. 정당명 정규화."""
    canon = load_party_canon()
    by_sido: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    page = 1
    while True:
        url = (f"{API}?serviceKey={key}&sgId={sg_id}&sgTypecode=8"
               f"&pageNo={page}&numOfRows=100")
        root = ET.fromstring(urllib.request.urlopen(url, timeout=40).read())
        if root.findtext("header/resultCode") != "INFO-00":
            break
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            sido = (it.findtext("sdName") or "").strip()
            party = (it.findtext("jdName") or "").strip()
            party = canon.get(party, party)
            if sido and party:
                by_sido[sido][party] += 1
        total = int(root.findtext("body/totalCount") or 0)
        if page * 100 >= total:
            break
        page += 1
    return by_sido


def build_races(by_sido) -> list[dict]:
    races = []
    for sido, parties in by_sido.items():
        ranked = sorted(parties.items(), key=lambda kv: -kv[1])
        cands = [{
            "name": p, "party": p, "votes": None, "pct": None,
            "rank": i + 1, "seats": n, "won": True,
        } for i, (p, n) in enumerate(ranked)]
        races.append({
            "sg_typecode": "8", "sido": sido, "sigungu": "",
            "scope": "proportional_sido", "votes_pending": True,
            "seats_total": sum(parties.values()), "candidates": cands,
        })
    return races


def backfill(n: int, key: str, dry: bool) -> bool:
    fid, sg_id = ELECTIONS[n]
    path = RESULTS / f"{fid}.json"
    if not path.exists():
        print(f"  {fid}: 파일 없음 — skip"); return False
    by_sido = fetch_metro_prop(key, sg_id)
    if not by_sido:
        print(f"  {fid}: API 비례 결과 없음 — skip"); return False
    data = json.loads(path.read_text())
    races = data.get("races", [])
    # 기존 tc=8 제거 후 교체(재실행 idempotent)
    races = [r for r in races if r.get("sg_typecode") != "8"]
    new_races = build_races(by_sido)
    races.extend(new_races)
    data["races"] = races
    total = sum(sum(p.values()) for p in by_sido.values())
    nat = defaultdict(int)
    for parties in by_sido.values():
        for p, c in parties.items():
            nat[p] += c
    summary = " · ".join(f"{p} {c}" for p, c in sorted(nat.items(), key=lambda kv: -kv[1]))
    print(f"  {fid}: 광역비례 {total}석 / {len(new_races)}시도 — {summary}{' [dry]' if dry else ''}")
    if not dry:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return not dry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, help="한 회차만 (3 또는 4)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = load_key()
    targets = [args.n] if args.n else list(ELECTIONS)
    print(f"광역 비례(tc=8) 백필 — {len(targets)}개 회차")
    for n in targets:
        backfill(n, key, args.dry_run)


if __name__ == "__main__":
    main()
