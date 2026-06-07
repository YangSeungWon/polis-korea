"""리얼미터 대통령 국정수행 평가 타깃 추출 → data/polls/approval_realmeter.json.

리얼미터 정례조사 PDF는 괘선(+---+) ASCII 표라 extract_text가 행을 잘 보존한다.
'◈ ○○○ 대통령 국정수행 평가' 표의 **'전 체' 행**에서:
  ①매우잘한다 ②잘하는편 ③잘못하는편 ④매우잘못함 [◐긍정 ◐부정] 모름 [계]
긍정 = ①+②, 부정 = ③+④ (집계열 ◐와 일치). 4단 합+모름 ≈ 100 검증.
subject = 조사일 현직 대통령(president_on), 직무정지 기간 제외(extract_approval_gallup.subject_for).

리얼미터는 갤럽과 달리 월별 통합 표가 없어(현재 조사 1건) 달 매칭 불필요.

사용:
  python3 scripts/parse/extract_approval_realmeter.py            # 리얼미터 전국 전수
  python3 scripts/parse/extract_approval_realmeter.py --limit 30 --debug
"""
from __future__ import annotations
import argparse
import glob
import json
import re
import sys
from pathlib import Path

import pdfplumber
import fitz  # pymupdf — 빠른 prefilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "parse"))
sys.path.insert(0, str(ROOT / "scripts" / "build"))
from parse_pdf_v2 import _repair_cid  # noqa: E402
from cid_decode import repair_text, needs_repair  # noqa: E402
from extract_approval import load_meta  # noqa: E402
from extract_approval_gallup import subject_for  # noqa: E402

OUT = ROOT / "data" / "polls" / "approval_realmeter.json"
_JOB = re.compile(r"국정\s*수행")
_DEC = re.compile(r"\d+\.\d+")
_TOTAL = re.compile(r"전\s*체")


def find_job_pages(pp: str) -> list[int]:
    try:
        doc = fitz.open(pp)
    except Exception:
        return []
    out = []
    try:
        for i in range(len(doc)):
            t = doc[i].get_text()
            if needs_repair(t):
                t = repair_text(t)
            if _JOB.search(t):
                out.append(i)
    finally:
        doc.close()
    return out


def extract_page(pg, debug=False) -> dict | None:
    """'국정수행 평가' 표의 첫 '전 체' 행에서 긍정(①+②)·부정(③+④)."""
    txt = _repair_cid(pg.extract_text() or "")
    lines = txt.split("\n")
    for i, ln in enumerate(lines):
        # 표 제목: '국정수행 평가'(2019+) 또는 '국정수행지지도'(2016 일간). ▣/■ 데이터행 제외.
        if "국정수행" not in ln or ln.strip().startswith("|"):
            continue
        # 제목 아래 ~15줄에서 첫 '전 체' 행
        for ln2 in lines[i + 1:i + 16]:
            if not _TOTAL.search(ln2.replace(" ", "")[:8]):
                # '전체'가 행 맨앞 라벨일 때만 (지역/계층 행 라벨 아님)
                lab = re.sub(r"[^가-힣]", "", ln2.split("|")[1] if "|" in ln2 else ln2[:12])
                if not lab.startswith("전체"):
                    continue
            pcts = [float(x) for x in _DEC.findall(ln2)]
            if len(pcts) < 4:
                continue
            a, b, c, d = pcts[0], pcts[1], pcts[2], pcts[3]
            pos, neg = a + b, c + d
            sum4 = a + b + c + d
            if debug:
                print(f"      전체행: {pcts[:8]} → 긍정{pos:.1f} 부정{neg:.1f} sum4{sum4:.1f}", file=sys.stderr)
            # 4단 합 ≈ 100 (모름 0~15). 집계열 있으면 pcts[4]≈pos로 교차검증.
            if 85 <= sum4 <= 100.5 and pos > 0 and neg > 0:
                if len(pcts) >= 6 and abs(pcts[4] - pos) > 1.5 and abs(pcts[4] - neg) > 1.5:
                    # 5번째 값이 긍/부 집계와 안 맞으면 컬럼 해석 의심 → skip
                    pass
                return {"positive": round(pos, 1), "negative": round(neg, 1)}
        return None  # 국정 제목은 찾았으나 전체행 해석 실패
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--incremental", action="store_true", help="기존 출력 보존·신규 ntt만(CI)")
    args = ap.parse_args()

    prev, done = [], set()
    if args.incremental and OUT.exists():
        prev = json.loads(OUT.read_text()).get("records", [])
        done = {r["ntt_id"] for r in prev}

    meta = load_meta()
    def is_nat(m):
        r = (m.get("region") or "").strip()
        return (not r) or r.startswith("전국")
    ids = {nid for nid, m in meta.items()
           if "리얼미터" in (m.get("agency") or "") and is_nat(m)}
    pdfs = sorted(p for p in glob.glob(str(ROOT / "data/raw/pdf/*.pdf"))
                  if Path(p).name.split("_", 1)[0] in ids)
    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"리얼미터 전국 PDF {len(pdfs)}개 스캔", file=sys.stderr)

    by_ntt: dict[str, dict] = {}
    for i, pp in enumerate(pdfs):
        nid = Path(pp).name.split("_", 1)[0]
        if nid in by_ntt or nid in done:
            continue
        pages = find_job_pages(pp)
        if not pages:
            continue
        if args.debug:
            print(f"--- {nid} jobpages{pages[:6]}", file=sys.stderr)
        try:
            with pdfplumber.open(pp) as doc:
                for pidx in pages:
                    r = extract_page(doc.pages[pidx], debug=args.debug)
                    if r:
                        by_ntt[nid] = r
                        if args.debug:
                            print(f"    → p{pidx} {r}", file=sys.stderr)
                        break
        except Exception as e:
            if args.debug:
                print(f"    ERR {e}", file=sys.stderr)
        if (i + 1) % 60 == 0:
            print(f"  {i+1}/{len(pdfs)} — {len(by_ntt)}건", file=sys.stderr)

    records = []
    for nid, r in by_ntt.items():
        m = meta[nid]
        ps = m.get("survey_start", "") or ""
        pe = m.get("survey_end", "") or ps
        subj = subject_for(pe or ps)
        if not subj:
            continue
        records.append({
            "ntt_id": nid, "agency": m.get("agency", ""),
            "period_start": ps, "period_end": pe,
            "subject": subj, "positive": r["positive"], "negative": r["negative"],
            "source_url": m.get("source_url", ""),
        })
    records = prev + records
    records.sort(key=lambda x: x["period_end"] or "")
    print(f"리얼미터 국정평가 {len(records)}건", file=sys.stderr)
    if args.dry_run or args.debug:
        from collections import Counter
        print("subject:", Counter(r["subject"] for r in records), file=sys.stderr)
        return
    OUT.write_text(json.dumps({"_meta": {"metric": "대통령 국정수행 평가 (리얼미터)",
                   "n": len(records)}, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
