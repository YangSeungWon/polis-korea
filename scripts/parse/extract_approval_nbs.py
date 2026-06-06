"""NBS(전국지표조사) 대통령 국정운영 평가 타깃 추출 → data/polls/approval_nbs.json.

NBS = 엠브레인퍼블릭·케이스탯·코리아리서치·한국리서치 컨소시엄 격주 조사.
갤럽·리얼미터가 thin한 윤석열 임기(2022~2024) 커버에 핵심.

'(NBS) 통계표'의 <표1> 국정운영 평가 — '전체' 행:
  ①매우잘하고있다 ②잘하는편 ③잘못하는편 ④매우잘못 모름 T2(①+②) B2(③+④) 계
정수% (소수 아님). 긍정 = ①+②, 부정 = ③+④. ①+②+③+④+모름 ≈ 100 검증.
표2(잘하는 점)·표3(잘못하는 점)·표4(신뢰도)는 4단 합이 100 안 돼 자동 배제 + 제목 필터.
목차(<표..> 페이지)는 전체행 없어 자동 우회. subject=president_on(직무정지 제외).

사용:
  python3 scripts/parse/extract_approval_nbs.py [--limit N --debug]
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber
import fitz  # pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "parse"))
sys.path.insert(0, str(ROOT / "scripts" / "build"))
from parse_pdf_v2 import _repair_cid  # noqa: E402
from cid_decode import repair_text, needs_repair  # noqa: E402
from extract_approval import load_meta  # noqa: E402
from extract_approval_gallup import subject_for  # noqa: E402

OUT = ROOT / "data" / "polls" / "approval_nbs.json"
_JOB = re.compile(r"국정\s*운영|국정\s*수행")
_INT = re.compile(r"^\d{1,3}$")
_EXCLUDE_TITLE = ("잘하는", "잘못하는", "신뢰", "이유")  # 표2·3·4·평가이유 (approval 아님)


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
    rows = defaultdict(list)
    for w in pg.extract_words(x_tolerance=1.5):
        rows[round(w["top"] / 2) * 2].append((w["x0"], _repair_cid(w["text"])))
    tops = sorted(rows)

    # 국정운영/수행 '평가' 제목 행 y (잘하는점·신뢰도·평가이유 표 배제).
    title_y = None
    for top in tops:
        line = "".join(t for _, t in sorted(rows[top]))
        h = re.sub(r"[^가-힣]", "", line)
        if _JOB.search(line) and ("평가" in line or "지지" in line) and not any(x in h for x in _EXCLUDE_TITLE):
            title_y = top
            break
    if title_y is None:
        return None

    # 제목 아래(같은 표)의 첫 '전체' 행 — 다른 표의 전체행 오인 방지.
    for top in tops:
        if not (title_y < top < title_y + 110):
            continue
        ws = sorted(rows[top])
        lab = re.sub(r"[^가-힣]", "", "".join(t for _, t in ws))
        if not lab.startswith("전체"):
            continue
        ints = [int(t) for _, t in ws if _INT.match(t)]
        if len(ints) < 5:
            continue
        a, b, c, d, dk = ints[0], ints[1], ints[2], ints[3], ints[4]
        pos, neg, sum5 = a + b, c + d, a + b + c + d + dk
        if debug:
            print(f"      전체행 ints={ints[:9]} → 긍정{pos} 부정{neg} ①~④+모름={sum5}", file=sys.stderr)
        # ①+②+③+④+모름 ≈ 100 (approval 4단 구조 확인 — 이유·투표의향 표 배제)
        if 97 <= sum5 <= 103 and pos > 0 and neg > 0:
            return {"positive": float(pos), "negative": float(neg)}
        return None  # 제목 아래 첫 전체행이 approval 구조 아니면 이 page 포기
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    meta = load_meta()
    fmap = {}
    for f in os.listdir(ROOT / "data/raw/pdf"):
        if f.endswith(".pdf"):
            fmap.setdefault(f.split("_", 1)[0], f)
    # NBS 통계표만 (설문지 제외)
    ids = [nid for nid, m in meta.items()
           if "NBS" in fmap.get(nid, "") and "통계표" in fmap.get(nid, "")]
    pdfs = sorted(str(ROOT / "data/raw/pdf" / fmap[nid]) for nid in ids)
    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"NBS 통계표 PDF {len(pdfs)}개 스캔", file=sys.stderr)

    by_ntt: dict[str, dict] = {}
    for i, pp in enumerate(pdfs):
        nid = Path(pp).name.split("_", 1)[0]
        if nid in by_ntt:
            continue
        pages = find_job_pages(pp)
        if not pages:
            continue
        try:
            with pdfplumber.open(pp) as doc:
                for pidx in pages:
                    r = extract_page(doc.pages[pidx], debug=args.debug)
                    if r:
                        by_ntt[nid] = r
                        if args.debug:
                            print(f"  {nid} → p{pidx} {r}", file=sys.stderr)
                        break
        except Exception as e:
            if args.debug:
                print(f"  {nid} ERR {e}", file=sys.stderr)
        if (i + 1) % 30 == 0:
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
    records.sort(key=lambda x: x["period_end"] or "")
    print(f"NBS 국정평가 {len(records)}건", file=sys.stderr)
    if args.dry_run or args.debug:
        from collections import Counter
        print("subject:", Counter(r["subject"] for r in records), file=sys.stderr)
        return
    OUT.write_text(json.dumps({"_meta": {"metric": "대통령 국정운영 평가 (NBS 전국지표조사)",
                   "n": len(records)}, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
