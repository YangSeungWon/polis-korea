"""결과 PDF 없는 pending polls의 첨부 PDF 재fetch.

scrape_nesdc는 신규 nttId만 처리하므로, 등록 시점에 질문지만 있다가 나중에 결과
PDF 추가 첨부된 경우를 못 잡는다. 19272 모노/무안군 같이 NESDC에 결과 PDF가
실제로 있는데 다운로드 누락된 케이스 복구.

흐름:
1. nesdc_9th_polls.csv 모든 ntts 중 결과 PDF 없는 것들 추출
2. 각 ntt의 NESDC detail page에서 첨부 list 재취득
3. RESULT_KEYWORDS 매치하는 파일이 새로 있으면 다운로드
"""
from __future__ import annotations
import csv
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scrape_nesdc import (  # noqa: E402
    parse_detail, detail_iter, download_pdfs, FILE_URL, HEADERS, RESULT_KEYWORDS,
)

ROOT = Path(__file__).resolve().parents[2]
META_CSV = ROOT / "data/raw/nesdc_9th_polls.csv"
PDF_DIR = ROOT / "data/raw/pdf"


def has_result_pdf(nid: str) -> bool:
    """이미 결과(키워드 매치) PDF가 다운로드되어있는지."""
    for p in PDF_DIR.glob(f"{nid}_*.pdf"):
        if any(k in p.name for k in RESULT_KEYWORDS):
            return True
    return False


def main():
    import argparse
    from datetime import date
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-days", type=int, default=30,
                    help="survey_end 기준 최근 N일 이내만 검사 (기본 30). "
                         "0이면 무제한. 오래된 ntt는 결과 영원히 미게시 가능성 높아 skip.")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(META_CSV, encoding="utf-8")))
    pending = [r for r in rows if not has_result_pdf(r["ntt_id"])]
    n_total = len(pending)
    if args.max_days > 0:
        today = date.today()
        def _within(r):
            end = r.get("survey_end", "")[:10]
            if not end:
                return True  # 날짜 없으면 일단 검사 (보수적)
            try:
                d = date.fromisoformat(end)
                return (today - d).days <= args.max_days
            except Exception:
                return True
        pending = [r for r in pending if _within(r)]
    print(f"결과 PDF 없는 ntts: {n_total}건 → 최근 {args.max_days}일 이내 {len(pending)}건 검사",
          file=sys.stderr)
    n_ok = 0
    n_still = 0
    for r in pending:
        nid = r["ntt_id"]
        try:
            for _, html in detail_iter([nid], delay=0.3):
                d = parse_detail(html, nid)
                d["ntt_id"] = nid
                # 결과 PDF만 받기 (질문지 제외)
                saved = []
                pdfs = d.get("pdf_files", "")
                for triple in pdfs.split(";"):
                    parts = triple.split("|")
                    if len(parts) != 4:
                        continue
                    atch, file_sn, bbs_id, bbs_key = parts
                    url = (f"{FILE_URL}?atchFileId={atch}&fileSn={file_sn}"
                           f"&bbsId={bbs_id}&bbsKey={bbs_key}")
                    try:
                        rr = requests.get(url, headers=HEADERS, timeout=25, stream=True,
                                          allow_redirects=True)
                        rr.raise_for_status()
                    except Exception:
                        continue
                    cd = rr.headers.get("Content-Disposition", "")
                    fm = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
                    from urllib.parse import unquote
                    raw_name = unquote(fm.group(1)) if fm else f"{nid}_{file_sn}.pdf"
                    if not any(k in raw_name for k in RESULT_KEYWORDS):
                        rr.close()
                        continue
                    safe = re.sub(r'[\\/<>:"|?*\x00-\x1f]', "_", raw_name).strip()
                    out_path = PDF_DIR / f"{nid}_{file_sn}_{safe}"
                    if out_path.exists():
                        rr.close()
                        saved.append(out_path.name)
                        continue
                    with open(out_path, "wb") as f:
                        for chunk in rr.iter_content(8192):
                            f.write(chunk)
                    saved.append(out_path.name)
                    time.sleep(0.5)
                if saved:
                    n_ok += 1
                    print(f"  + {nid}: {len(saved)}장 | {saved[0][:50]}", file=sys.stderr)
                else:
                    n_still += 1
                break
        except Exception as e:
            print(f"  ! {nid}: {e}", file=sys.stderr)
            n_still += 1
        time.sleep(0.4)

    print(f"\n결과 PDF 신규 다운: {n_ok}건 / 여전히 없음: {n_still}건", file=sys.stderr)


if __name__ == "__main__":
    main()
