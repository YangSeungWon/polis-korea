"""data/raw/MANIFEST.json 기준으로 raw 파일 누락 점검.

다른 머신·새 clone에서 raw 데이터 상태 audit. 누락 파일은 source_kind별로
그룹화 + 재다운로드 명령 안내.

사용:
  python3 scripts/audit/verify_raw.py
  python3 scripts/audit/verify_raw.py --kind nesdc_poll_pdf   # 한 종류만
"""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "raw" / "MANIFEST.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", help="source_kind 필터")
    args = ap.parse_args()

    if not MANIFEST.exists():
        print(f"ERR: {MANIFEST} 없음 — scripts/build/build_raw_manifest.py 먼저")
        return

    m = json.loads(MANIFEST.read_text(encoding="utf-8"))

    missing = defaultdict(list)
    present = defaultdict(int)
    regen = {}

    # 일반 sources/refs/result_csv
    for rec in m.get("sources", []):
        sk = rec["source_kind"]
        if args.kind and sk != args.kind:
            continue
        path = ROOT / rec["path"]
        if path.exists():
            present[sk] += 1
        else:
            missing[sk].append(rec["path"])
            regen[sk] = rec.get("regenerate", "—")

    # PDF files
    if not args.kind or args.kind == "nesdc_poll_pdf":
        for rec in m.get("nesdc_pdf_files", []):
            path = ROOT / rec["path"]
            if path.exists():
                present["nesdc_poll_pdf"] += 1
            else:
                missing["nesdc_poll_pdf"].append(rec["path"])
                regen["nesdc_poll_pdf"] = "python3 scripts/fetch/scrape_nesdc.py  # 또는 redownload_orphans.py"

    print(f"manifest 시각: {m['_meta']['scanned_at']}")
    print(f"manifest 총 파일: {m['_meta']['total_files']:,}  ({m['_meta']['total_bytes']/1024/1024/1024:.2f} GB)\n")

    total_missing = 0
    for sk in sorted(set(list(present.keys()) + list(missing.keys()))):
        p = present[sk]
        mc = len(missing[sk])
        total_missing += mc
        mark = "✓" if mc == 0 else "!"
        print(f"  {mark} {sk:20} present {p:5,}  missing {mc:5,}")
        if mc and mc <= 10:
            for path in missing[sk][:10]:
                print(f"      · {path}")
        if mc:
            print(f"      → 재다운로드: {regen.get(sk, '—')}")
            print()

    if total_missing == 0:
        print("\n모든 raw 파일 present.")
    else:
        print(f"\n누락 합계: {total_missing:,} 파일")


if __name__ == "__main__":
    main()
