"""CID 폰트 parse_fail PDF에 OCR 하이브리드 적용 → parsed/ 갱신.

대상: audit가 parse_fail로 분류 + 텍스트층이 cid/모지바케인 등록(여론조사꽃 등).
숫자는 pdfplumber 좌표, 이름은 OCR로 — 신뢰 가능한 후보지지만 추출해 parsed JSON 덮어씀.
"""
from __future__ import annotations
import glob
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ROOT = Path(__file__).resolve().parents[2]


def cid_fail_pdfs() -> list[str]:
    fail = [l.split(" | ")[0] for l in subprocess.run(
        [sys.executable, "scripts/audit/audit_parse.py", "--list", "parse_fail"],
        capture_output=True, text=True).stdout.splitlines()]
    out = []
    for ntt in fail:
        gs = (glob.glob(f"data/raw/grids/{ntt}_*결과*.json")
              or glob.glob(f"data/raw/grids/{ntt}_*.json"))
        if not gs:
            continue
        d = json.loads(Path(gs[0]).read_text(encoding="utf-8"))
        txt = " ".join(p.get("page_text", "") for p in d.get("pages", [])[:6])
        if "(cid:" in txt or len(re.findall(r"[가-힣]", txt)) < 15:
            # 결과 PDF 우선
            pdfs = (glob.glob(f"data/raw/pdf/{ntt}_*결과*.pdf")
                    or glob.glob(f"data/raw/pdf/{ntt}_*집계*.pdf")
                    or glob.glob(f"data/raw/pdf/{ntt}_*.pdf"))
            if pdfs:
                out.append(pdfs[0])
    return out


def _work(pdf_str: str) -> tuple[str, int]:
    import ocr_hybrid
    pdf = Path(pdf_str)
    r = ocr_hybrid.extract_pdf(pdf)  # auto candidate_pages
    out = ROOT / "data/raw/parsed" / (pdf.stem + ".json")
    out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return pdf.name, len([q for q in r["questions"] if q["candidates"]])


def main():
    pdfs = cid_fail_pdfs()
    print(f"CID parse_fail PDF: {len(pdfs)}개 OCR 추출 시작", file=sys.stderr)
    t = time.time()
    n_ok = n_q = 0
    with ProcessPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(_work, p) for p in pdfs]
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                name, nq = fut.result()
                n_ok += 1
                n_q += nq
            except Exception as e:
                print(f"  FAIL {e}", file=sys.stderr)
            if i % 20 == 0:
                print(f"  {i}/{len(pdfs)} ({time.time()-t:.0f}s, 누적 {n_q}문항)", file=sys.stderr)
    print(f"완료: {n_ok} PDF, {n_q} 후보지지 문항 / {time.time()-t:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
