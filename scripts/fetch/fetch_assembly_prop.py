"""data.go.kr 당선인 정보 API → 국회의원 비례대표(sgTypecode=7) 정당별 의석 회수·백필.

17~21대 총선 데이터는 지역구 당선만 있고 비례 의석 배분이 비어 있었다(nation race
candidate.proportional_seats = None). NEC 당선인 API가 비례 당선인을 전원 주므로
정당(jdName)별로 세어 nation race 후보의 proportional_seats에 기록한다.
→ '의회 구성' 표·히어로 반원이 지역구+비례 합산으로 정확해진다.

매칭: nation race 후보 party == API jdName (같은 선거 당시 정당명이라 그대로 일치).

사용:
  NEC_API_KEY=... python scripts/fetch/fetch_assembly_prop.py            # 17~21대 전부
  NEC_API_KEY=... python scripts/fetch/fetch_assembly_prop.py --dry-run  # 저장 없이 확인
  NEC_API_KEY=... python scripts/fetch/fetch_assembly_prop.py --id 21st-general-2020
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
API = "https://apis.data.go.kr/9760000/WinnerInfoInqireService2/getWinnerInfoInqire"

# 총선 회차 → (결과 파일 id, 선거일 sgId). 비례 의석이 비어 있던 17~21대가 대상.
# 22대는 이미 채워져 있으나 재검증용으로 포함(동일값이면 no-op).
ELECTIONS = {
    "17th-general-2004": "20040415",
    "18th-general-2008": "20080409",
    "19th-general-2012": "20120411",
    "20th-general-2016": "20160413",
    "21st-general-2020": "20200415",
    "22nd-general-2024": "20240410",
}


def load_key() -> str:
    key = os.environ.get("NEC_API_KEY")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("NEC_API_KEY"):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        sys.exit("NEC_API_KEY 없음 (.env 또는 환경변수)")
    return key


def fetch_prop_seats(key: str, sg_id: str) -> Counter:
    """sgTypecode=7 비례대표 당선인 → 정당(jdName)별 의석 수."""
    cnt: Counter = Counter()
    page = 1
    while True:
        url = (f"{API}?serviceKey={key}&sgId={sg_id}&sgTypecode=7"
               f"&pageNo={page}&numOfRows=100")
        root = ET.fromstring(urllib.request.urlopen(url, timeout=40).read())
        if root.findtext("header/resultCode") != "INFO-00":
            break
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            jd = (it.findtext("jdName") or "").strip()
            if jd:
                cnt[jd] += 1
        total = int(root.findtext("body/totalCount") or 0)
        if page * 100 >= total:
            break
        page += 1
    return cnt


def backfill(fid: str, sg_id: str, key: str, dry: bool) -> bool:
    path = RESULTS / f"{fid}.json"
    if not path.exists():
        print(f"  {fid}: 파일 없음 — skip")
        return False
    api = fetch_prop_seats(key, sg_id)
    if not api:
        print(f"  {fid}: API 비례 결과 없음 — skip")
        return False
    data = json.loads(path.read_text())
    nats = [r for r in data.get("races", []) if r.get("scope") == "nation"]
    if not nats:
        print(f"  {fid}: nation race 없음 — skip")
        return False
    nat = nats[0]
    cands = nat.get("candidates", [])
    ours = {c.get("party") for c in cands}
    unmatched = [p for p in api if p not in ours]
    # 매칭 안 되는 정당(우리 후보 목록에 없는 비례 정당)은 후보로 추가.
    for p in unmatched:
        cands.append({"name": p, "party": p, "votes": None, "pct": None})
    changed = 0
    for c in cands:
        n = api.get(c.get("party"), 0)
        if c.get("proportional_seats") != n:
            c["proportional_seats"] = n
            changed += 1
        else:
            c["proportional_seats"] = n
    total = sum(api.values())
    summary = " ".join(f"{p} {n}" for p, n in api.most_common())
    flag = " ⚠ 신규정당:" + ",".join(unmatched) if unmatched else ""
    print(f"  {fid}: 비례 {total}석 ({summary}){flag}{' [dry]' if dry else ''}")
    if not dry and changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return changed > 0 and not dry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="한 회차만 (예: 21st-general-2020)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = load_key()
    targets = {args.id: ELECTIONS[args.id]} if args.id else ELECTIONS
    if args.id and args.id not in ELECTIONS:
        sys.exit(f"알 수 없는 id: {args.id}")
    print(f"비례 의석 백필 — {len(targets)}개 회차")
    wrote = 0
    for fid, sgid in targets.items():
        if backfill(fid, sgid, key, args.dry_run):
            wrote += 1
    print(f"완료 — {wrote}개 파일 갱신{' (dry-run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
