"""한국리서치 대통령 국정운영 평가 타깃 추출 → data/polls/approval_hrc.json.

한국리서치 단독 조사(NBS 컨소시엄 아님)는 헤더에 '긍정평가(①+②)'·'부정평가(③+④)'
집계 컬럼이 명시된 소수% 표. '전체' 행 소수%를 그 두 컬럼 x에 정렬해 추출.
2017 문재인 취임년 등 갤럽·리얼미터·NBS 공백 보강(문재인 2017-10 = 76.4/19.9).

NBS-format 한국리서치 파일(T2/B2 헤더, '긍정평가' 라벨 없음)은 자동으로 None → NBS 파서 담당.
제목에 '대통령' + 국정운영/국정수행/직무수행 (정당대표 직무평가 배제). subject=president_on(직무정지 제외).

사용: python3 scripts/parse/extract_approval_hrc.py [--limit N --debug]
"""
from __future__ import annotations
import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber
import fitz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "parse"))
sys.path.insert(0, str(ROOT / "scripts" / "build"))
from parse_pdf_v2 import _repair_cid  # noqa: E402
from cid_decode import repair_text, needs_repair  # noqa: E402
from extract_approval import load_meta  # noqa: E402
from extract_approval_gallup import subject_for  # noqa: E402

OUT = ROOT / "data" / "polls" / "approval_hrc.json"
_JOB = re.compile(r"국정\s*운영|국정\s*수행|직무\s*수행")
_DEC = re.compile(r"^\d{1,3}\.\d$")


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
            # 대통령 국정 표만 (정당대표 직무평가 배제)
            if _JOB.search(t) and "대통령" in t:
                out.append(i)
    finally:
        doc.close()
    return out


def extract_page(pg, debug=False) -> dict | None:
    rows = defaultdict(list)
    for w in pg.extract_words(x_tolerance=1.5):
        rows[round(w["top"] / 2) * 2].append(((w["x0"] + w["x1"]) / 2, _repair_cid(w["text"])))
    tops = sorted(rows)

    # 제목: 국정운영/수행 평가 (page-level 대통령은 find_job_pages가 보장 → 정당대표 직무 배제)
    title_y = None
    for top in tops:
        line = "".join(t for _, t in sorted(rows[top]))
        if _JOB.search(line) and "평가" in line:
            title_y = top
            break
    if title_y is None:
        return None

    # 집계 컬럼 x중심 (헤더) — '긍정평가/부정평가' 또는 '①+②/③+④' 라벨.
    pos_x = neg_x = dk_x = None
    for top in tops:
        for xc, t in rows[top]:
            h = re.sub(r"[^가-힣]", "", t)
            if (h.startswith("긍정평가") or ("①" in t and "②" in t)) and pos_x is None:
                pos_x = xc
            elif (h.startswith("부정평가") or ("③" in t and "④" in t)) and neg_x is None:
                neg_x = xc
            elif h.startswith("모름") and dk_x is None:
                dk_x = xc
    if pos_x is None or neg_x is None:
        return None

    # '전체' 행 소수% 정렬
    for top in tops:
        if top <= title_y:
            continue
        ws = sorted(rows[top])
        lab = re.sub(r"[^가-힣]", "", "".join(t for _, t in ws))
        if not lab.startswith("전체"):
            continue
        pcts = [(xc, float(t)) for xc, t in ws if _DEC.match(t)]
        if len(pcts) < 3:
            continue

        def near(cx):
            return min(pcts, key=lambda p: abs(p[0] - cx))

        pos, neg = near(pos_x)[1], near(neg_x)[1]
        tot = pos + neg + (near(dk_x)[1] if dk_x else 0)
        if debug:
            print(f"      전체행 긍정{pos} 부정{neg} (+모름→{tot})", file=sys.stderr)
        if pos > 0 and neg > 0 and (80 <= pos + neg <= 100 or 96 <= tot <= 104):
            return {"positive": round(pos, 1), "negative": round(neg, 1)}
        return None
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
           if "한국리서치" in (m.get("agency") or "") and is_nat(m)}
    pdfs = sorted(p for p in glob.glob(str(ROOT / "data/raw/pdf/*.pdf"))
                  if Path(p).name.split("_", 1)[0] in ids)
    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"한국리서치 전국 PDF {len(pdfs)}개 스캔", file=sys.stderr)

    by_ntt: dict[str, dict] = {}
    for i, pp in enumerate(pdfs):
        nid = Path(pp).name.split("_", 1)[0]
        if nid in by_ntt or nid in done:
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
        if (i + 1) % 40 == 0:
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
    print(f"한국리서치 국정평가 {len(records)}건", file=sys.stderr)
    if args.dry_run or args.debug:
        from collections import Counter
        print("subject:", Counter(r["subject"] for r in records), file=sys.stderr)
        return
    OUT.write_text(json.dumps({"_meta": {"metric": "대통령 국정운영 평가 (한국리서치)",
                   "n": len(records)}, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
