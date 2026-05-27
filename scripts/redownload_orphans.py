"""미수집(orphan) 등록의 결과 PDF를 NESDC에서 재다운로드.

image_no_table로 분류됐지만 실은 PDF가 안 받아진 등록(메타엔 pdf_files 토큰 존재).
scrape_nesdc.download_pdfs로 결과 PDF만 재수집. NESDC 부하 줄이려 파일·등록 간 딜레이.
"""
from __future__ import annotations
import csv
import glob
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrape_nesdc import download_pdfs, PDF_DIR, ROOT  # noqa: E402

META = ROOT / "data/raw/nesdc_9th_polls.csv"
NTT_DELAY = 1.0  # 등록 간 (파일 간은 download_pdfs의 pdf_delay)


def orphan_ntts() -> list[str]:
    img = [l.split(" | ")[0] for l in subprocess.run(
        [sys.executable, "scripts/audit_parse.py", "--list", "image_no_table"],
        capture_output=True, text=True).stdout.splitlines()]
    return [n for n in img if not glob.glob(f"data/raw/pdf/{n}_*.pdf")]


def main():
    rows = {r["ntt_id"]: r for r in csv.DictReader(open(META, encoding="utf-8"))}
    orphans = orphan_ntts()
    todo = [n for n in orphans if rows.get(n, {}).get("pdf_files")]
    print(f"orphan {len(orphans)} 중 pdf_files 있는 {len(todo)}개 재다운로드", file=sys.stderr)
    t = time.time()
    n_files = n_ntt = 0
    for i, ntt in enumerate(todo, 1):
        meta = {"ntt_id": ntt, "pdf_files": rows[ntt]["pdf_files"]}
        try:
            saved = download_pdfs(meta, PDF_DIR, result_only=True, pdf_delay=0.8)
        except Exception as e:
            print(f"  ! {ntt}: {e}", file=sys.stderr)
            saved = []
        if saved:
            n_ntt += 1
            n_files += len(saved)
        time.sleep(NTT_DELAY)
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} ({time.time()-t:.0f}s, {n_ntt}등록 {n_files}파일)", file=sys.stderr)
    print(f"완료: {n_ntt}등록 {n_files}파일 / {time.time()-t:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
