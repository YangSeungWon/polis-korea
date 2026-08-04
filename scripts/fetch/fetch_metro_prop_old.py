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
# 회차별 정당명 명시 override — NEC API가 시대-구명을 줄 때 데이터셋 표기로 통일.
#   2006(4회): API '새천년민주당'(2005 개명 전) → 데이터셋 '민주당(2005)'.
OVERRIDE = {
    4: {"민주당": "민주당(2005)"},   # 2006 API='민주당' → 데이터셋 '민주당(2005)' (2002는 API='새천년민주당'이라 그대로)
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


def alias_map() -> dict:
    """registry.json의 alias/약칭 → 정식명. (자민련→자유민주연합 등)"""
    reg = json.loads((ROOT / "data" / "parties" / "registry.json").read_text()).get("parties", {})
    m = {}
    for name, info in reg.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        if info.get("abbr"):
            m[info["abbr"]] = name
        for a in info.get("aliases", []):
            m[a] = name
    return m


def make_canon(existing: set, override: dict) -> "callable":
    """그 선거 데이터에 이미 있는 정당명 우선 유지 — 시대별 동명 정당(2006 '민주당' 등)을
    lineage 캐논으로 과잉 매핑하지 않게. 명시 override(회차별) → existing → registry alias 순."""
    al = alias_map()

    def cf(party: str) -> str:
        if party in override:        # 회차별 명시 매핑
            return override[party]
        if party in existing:
            return party
        c = al.get(party)
        if c and c in existing:
            return c
        return party
    return cf


def fetch_metro_prop(key: str, sg_id: str, canon):
    """sgTypecode=8 광역 비례 당선인 → {sido: {party: seats}}. 정당명 그 선거 표기로 정규화."""
    by_sido: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    page = 1
    while True:
        url = (f"{API}?serviceKey={key}&sgId={sg_id}&sgTypecode=8"
               f"&pageNo={page}&numOfRows=100&resultType=xml")
        root = ET.fromstring(urllib.request.urlopen(url, timeout=40).read())
        if root.findtext("header/resultCode") != "INFO-00":
            break
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            sido = (it.findtext("sdName") or "").strip()
            party = (it.findtext("jdName") or "").strip()
            party = canon(party)
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
    data = json.loads(path.read_text())
    # 그 선거에 이미 등장한 정당명 (지역구·단체장 등) — 비례 정당명을 여기에 맞춤.
    # tc=8(비례)은 제외 — 직전 run이 쓴 값에 자기오염되지 않게.
    existing = {c.get("party") for r in data.get("races", []) if r.get("sg_typecode") != "8"
                for c in (r.get("candidates") or []) if c.get("party")}
    by_sido = fetch_metro_prop(key, sg_id, make_canon(existing, OVERRIDE.get(n, {})))
    if not by_sido:
        print(f"  {fid}: API 비례 결과 없음 — skip"); return False
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
