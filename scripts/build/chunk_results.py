"""data/results/{id}.json (full) → 2개 청크로 분리.

archive 페이지는 nation/sido/district race만 쓰는데 sigungu-level race가
파일 크기의 80~90% 차지. 분리하면 archive 초기 fetch 92% 감량 (22대 총선
2.2MB → 162KB).

청크:
  {id}.json          — _meta + nation + sido + district race (archive용 lite)
                       _meta.chunked = true 표시
  {id}.sigungu.json  — sigungu + district_sigungu + sigungu_part race
                       (history 페이지 drill-down용)

idempotent — 이미 청크된 파일에 재실행하면 변경 없음. fetch_nec_results.py
실행 후 호출 (워크플로 단계).

사용:
  python3 scripts/build/chunk_results.py                 # 전체
  python3 scripts/build/chunk_results.py --id 22nd-general-2024
  python3 scripts/build/chunk_results.py --check         # diff만
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "data" / "results"

# {id}.json 패턴 (새 schema 회차별 파일).
#   N회/N대 형식: 22nd-general-2024.json
#   단독 재보궐: byelection-2021-04-07.json (date 기반, n번호 없음)
ID_PATS = [
    re.compile(r"^(\d+)(st|nd|rd|th)-(pres|general|local|byelection)-\d+\.json$"),
    re.compile(r"^byelection-\d{4}-\d{2}-\d{2}\.json$"),
]
ID_PAT = ID_PATS[0]  # 호환 유지

MAIN_SCOPES = {"nation", "sido", "district"}
DRILL_SCOPES = {"sigungu", "district_sigungu", "sigungu_part"}


def chunk(data: dict) -> tuple[dict, dict] | None:
    """전체 → (core, sigungu) 분할. 이미 청크되어 있으면 None.

    byelection은 데이터 작아 (~80 KB 이하) 청크 의미 없음 — skip.
    """
    if data.get("_meta", {}).get("chunked"):
        return None
    eid = (data.get("_meta") or {}).get("election_id", "")
    if eid.startswith("byelection-"):
        return None  # standalone 재보궐은 통째로 유지
    races = data.get("races", [])
    # 지선 광역의원(tc=5)·기초의원(tc=6)은 scope=district이지만 1500+ race로 가중 → drill chunk로.
    def is_drill(r):
        if r.get("scope") in DRILL_SCOPES:
            return True
        if r.get("sg_typecode") in ("5", "6") and r.get("scope") == "district":
            return True
        return False
    main_races = [r for r in races if not is_drill(r)]
    drill_races = [r for r in races if is_drill(r)]
    if not drill_races:
        return None  # 청크할 게 없음
    meta = dict(data.get("_meta", {}))
    meta["chunked"] = True
    meta["sigungu_file"] = "sigungu"
    core = {"_meta": meta, "races": main_races}
    sub_meta = {k: meta[k] for k in ("election", "election_id", "election_date") if k in meta}
    sub_meta["chunk_of"] = meta.get("election_id", "")
    sigungu = {"_meta": sub_meta, "races": drill_races}
    return core, sigungu


def process(path: Path, check: bool) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    result = chunk(data)
    if result is None:
        return "skip"
    core, sigungu = result
    sub_path = path.with_suffix(".sigungu.json")
    if check:
        return "would-chunk"
    path.write_text(json.dumps(core, ensure_ascii=False, indent=2), encoding="utf-8")
    sub_path.write_text(json.dumps(sigungu, ensure_ascii=False, indent=2), encoding="utf-8")
    return "chunked"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="특정 회차 1건만 (예: 22nd-general-2024)")
    ap.add_argument("--check", action="store_true", help="diff만 출력, 파일 안 씀")
    args = ap.parse_args()

    targets = []
    for f in sorted(RESULTS_DIR.iterdir()):
        if not f.is_file() or not f.name.endswith(".json"):
            continue
        if not any(p.match(f.name) for p in ID_PATS):
            continue
        if args.id and not f.name.startswith(args.id + "."):
            continue
        targets.append(f)

    if not targets:
        print("대상 0건")
        return

    counts = {"chunked": 0, "would-chunk": 0, "skip": 0}
    for f in targets:
        before = f.stat().st_size
        status = process(f, args.check)
        counts[status] = counts.get(status, 0) + 1
        if status in ("chunked", "would-chunk"):
            sub = f.with_suffix(".sigungu.json")
            sub_sz = sub.stat().st_size if sub.exists() else 0
            after = f.stat().st_size if status == "chunked" else before
            print(f"  {f.name}: {before//1024} KB → core {after//1024} KB + sigungu {sub_sz//1024} KB")
    print(f"\n청크 {counts.get('chunked', 0)} · 예정 {counts.get('would-chunk', 0)} · 스킵 {counts.get('skip', 0)}")


if __name__ == "__main__":
    main()
