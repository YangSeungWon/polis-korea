"""PDF → 표 격자 캐시. Step A (격자 추출)만 분리한 expensive 단계.

비용 큰 단계 (PDF 열기 + pdfplumber.extract_tables)를 한 번만 돌리고
`data/raw/grids/{pdf_stem}.json`에 캐시. Step B/C (parse_from_grids) 룰 변경 시
재실행할 필요 없음.

사용:
    .venv/bin/python scripts/extract_grids.py 'data/raw/pdf/*.pdf' --jobs 8
    .venv/bin/python scripts/extract_grids.py 'data/raw/pdf/*.pdf' --skip-existing  # 새 PDF만
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_pdf_v2 import extract_grids_from_pdf  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
GRIDS_DIR = ROOT / "data/raw/grids"


def _process_one(args_tuple: tuple[str, str]) -> tuple[str, int, str]:
    pdf_path_str, out_dir_str = args_tuple
    pdf_path = Path(pdf_path_str)
    out_dir = Path(out_dir_str)
    try:
        grids = extract_grids_from_pdf(pdf_path)
    except Exception as e:
        return (pdf_path.name, 0, str(e))
    n_tables = sum(len(p.get("tables", [])) for p in grids.get("pages", []))
    out_path = out_dir / (pdf_path.stem + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(grids, f, ensure_ascii=False, indent=2)
    return (pdf_path.name, n_tables, "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="PDF 파일 또는 글로브")
    ap.add_argument("--out-dir", default="data/raw/grids", help="격자 캐시 저장 디렉토리")
    ap.add_argument("--skip-existing", action="store_true", help="이미 캐시 있으면 skip")
    ap.add_argument("--jobs", type=int, default=4, help="병렬 워커 수")
    args = ap.parse_args()

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    targets: list[Path] = []
    for inp in args.inputs:
        for path in sorted(Path(".").glob(inp) if "*" in inp else [Path(inp)]):
            if args.skip_existing and (out_dir / (path.stem + ".json")).exists():
                continue
            targets.append(path)

    print(f"격자 추출: {len(targets)} PDFs → {out_dir}", file=sys.stderr)

    n_ok = n_fail = 0
    if args.jobs <= 1:
        for path in targets:
            name, n, err = _process_one((str(path), str(out_dir)))
            if err:
                print(f"FAIL {name}: {err}", file=sys.stderr); n_fail += 1
            else:
                n_ok += 1
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futs = [ex.submit(_process_one, (str(p), str(out_dir))) for p in targets]
            for i, fut in enumerate(as_completed(futs), 1):
                name, n, err = fut.result()
                if err:
                    print(f"FAIL {name}: {err}", file=sys.stderr); n_fail += 1
                else:
                    n_ok += 1
                if i % 100 == 0:
                    print(f"  진행 {i}/{len(targets)}", file=sys.stderr)

    print(f"완료: OK {n_ok}, FAIL {n_fail}", file=sys.stderr)


if __name__ == "__main__":
    main()
