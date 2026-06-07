"""대통령 국정수행 평가(국정 지지율) 추출 — 전 회차 PDF → data/polls/approval.json.

국정평가 표는 후보/정당 표와 구조가 달라(긍정/부정 평가 단계) parse_pdf_v2가 skip한다.
선거 무관 상시 지표라 회차별 aggregated가 아닌 **연속 시계열** 하나로 모은다 (tracker 페이지).

표 양식: "○○ 정부 국정수행(능력) 평가" — 매우잘함/대체로잘함/대체로못함/매우못함(+모름)
단계별 행, 또는 긍정평가/부정평가 집계행. 괘선없는 cross-tab이라 recover_flower처럼
extract_words로 행(y) 그룹화 → 평가단계 라벨행의 전체(첫 pct) 채택.
긍정평가 = 잘함 합(또는 집계행), 부정평가 = 못함 합.

subject(현직 대통령)는 질문 텍스트 "○○ 정부 국정수행"에서. region → sido(전국='').

사용:
  python3 scripts/parse/extract_approval.py            # 전 회차 CSV PDF 스캔
  python3 scripts/parse/extract_approval.py --limit 50 # 테스트
"""
from __future__ import annotations
import argparse
import csv
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber
import fitz  # pymupdf — 빠른 텍스트 prefilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "parse"))
sys.path.insert(0, str(ROOT / "scripts" / "build"))
from parse_pdf_v2 import _repair_cid  # noqa: E402
from cid_decode import repair_text, needs_repair  # noqa: E402
from build_polls import canon_sido, SIDO_CANONICAL, parse_survey_period  # noqa: E402

# 회차별 NESDC CSV (ntt → 메타). 전 회차 통합 — 국정평가는 선거 무관.
CSV_FILES = [
    "nesdc_9th_polls.csv", "nesdc_8th_polls.csv", "nesdc_7th_polls.csv",
    "nesdc_22gen_polls.csv", "nesdc_21gen_polls.csv", "nesdc_20gen_polls.csv",
    "nesdc_21pres_polls.csv", "nesdc_20pres_polls.csv", "nesdc_19pres_polls.csv",
    "nesdc_etc_polls.csv",   # VT012 '기타' = 선거 무관 전국 정기(정례) 정당지지/국정 — 연속 트래킹 핵심
]
OUT = ROOT / "data" / "polls" / "approval.json"

_APPROVAL_PAGE = re.compile(r"국정\s*(수행|운영)\s*(평가|능력)|직무\s*수행\s*(평가|긍정)")
_PCT = re.compile(r"^\d{1,3}\.\d$")

# 현직 대통령 임기 (국정평가 subject — 조사일 기준). 윤석열 탄핵 파면 2025-04-04,
# 한덕수 권한대행~2025-06, 이재명 취임 2025-06-04.
PRESIDENT_TERMS = [
    ("2008-02-25", "2013-02-24", "이명박"),
    ("2013-02-25", "2017-03-10", "박근혜"),
    ("2017-05-10", "2022-05-09", "문재인"),
    ("2022-05-10", "2025-04-04", "윤석열"),
    ("2025-06-04", "2030-12-31", "이재명"),
]


def president_on(date: str) -> str:
    for a, b, name in PRESIDENT_TERMS:
        if a <= date <= b:
            return name
    return ""
POS_LABELS = ("긍정평가", "매우잘하고있다", "대체로잘하는편이다", "잘하고있다", "매우잘함", "대체로잘함", "잘하는편")
NEG_LABELS = ("부정평가", "대체로잘못하는편이다", "매우잘못하고있다", "잘못하고있다", "매우못함", "대체로못함", "못하는편")
AGG_POS, AGG_NEG = "긍정평가", "부정평가"


def load_meta() -> dict[str, dict]:
    meta = {}
    for f in CSV_FILES:
        p = ROOT / "data" / "raw" / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            meta.setdefault(r["ntt_id"], r)
    return meta


def region_sido(region: str) -> str:
    """전국·복합권역 → '' (national). 단일 시도 → canonical."""
    if not region or region.startswith("전국"):
        return ""
    toks = [canon_sido(t) for t in region.split() if t not in ("전체", "전지역", "전 지역")]
    sidos = {t for t in toks if t in SIDO_CANONICAL.values()}
    return next(iter(sidos)) if len(sidos) == 1 else ""


def find_approval_pages(pp: str) -> list[int]:
    """fitz로 국정평가 키워드 매칭 page index **전부** (목차 page도 포함 — extract가 검증)."""
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
            if _APPROVAL_PAGE.search(t):
                out.append(i)
    finally:
        doc.close()
    return out


def _classify(label: str) -> str:
    if AGG_POS in label:
        return "AP"
    if AGG_NEG in label:
        return "AN"
    if any(l in label for l in POS_LABELS):
        return "P"
    if any(l in label for l in NEG_LABELS):
        return "N"
    return ""


def extract_page(pg, repair) -> dict | None:
    """국정평가 page → {positive, negative}. 레이아웃 A(평가단계=행)·B(평가단계=열) 둘 다."""
    rows: dict = defaultdict(list)
    for w in pg.extract_words(x_tolerance=1.5):
        rows[round(w["top"] / 3) * 3].append((w["x0"], (w["x0"] + w["x1"]) / 2, repair(w["text"])))

    # 레이아웃 A: 한 행에 평가단계 라벨 + 전체 pct
    agg = {}
    sumv = {"P": 0.0, "N": 0.0}
    for top in sorted(rows):
        ws = sorted(rows[top])
        label = re.sub(r"[^가-힣]", "", "".join(t for _, _, t in ws))
        pcts = [float(t) for _, _, t in ws if _PCT.match(t)]
        cl = _classify(label)
        if cl and pcts:
            if cl in ("AP", "AN"):
                agg[cl] = pcts[0]
            else:
                sumv[cl] += pcts[0]
    pos = agg.get("AP", sumv["P"] or None)
    neg = agg.get("AN", sumv["N"] or None)
    if pos and neg and 30 <= pos + neg <= 105:
        return {"positive": round(pos, 1), "negative": round(neg, 1)}

    # 레이아웃 B: 평가단계가 컬럼 헤더 + '전체' 행에 pct (x 정렬)
    total_top = None
    total_pcts = []  # (xc, pct)
    for top in sorted(rows):
        ws = sorted(rows[top])
        lab = re.sub(r"[^가-힣]", "", "".join(t for _, _, t in ws))
        if lab.startswith("전체") or lab.startswith("전 체".replace(" ", "")):
            cand = [(xc, float(t)) for _, xc, t in ws if _PCT.match(t)]
            if len(cand) >= 2:
                total_top, total_pcts = top, cand
                break
    if total_top is None:
        return None
    # 헤더(전체행 위)에서 평가단계 컬럼 x 수집
    cols = []  # (xc, class)
    for top in sorted(rows):
        if not (total_top - 80 <= top < total_top):
            continue
        # 같은 컬럼의 다줄 라벨 합치려 단어별 분류
        for x0, xc, t in rows[top]:
            cl = _classify(re.sub(r"[^가-힣]", "", t))
            if cl:
                cols.append((xc, cl))
    pos = neg = 0.0
    used = set()
    for xc, cl in cols:
        best = min(((i, p) for i, p in enumerate(total_pcts) if i not in used),
                   key=lambda ip: abs(ip[1][0] - xc), default=None)
        if best is None:
            continue
        i, (_, pct) = best
        used.add(i)
        if cl in ("P", "AP"):
            pos += pct
        else:
            neg += pct
    if pos and neg and 30 <= pos + neg <= 105:
        return {"positive": round(pos, 1), "negative": round(neg, 1)}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    meta = load_meta()
    ids = set(meta)
    pdfs = sorted(p for p in glob.glob(str(ROOT / "data/raw/pdf/*.pdf"))
                  if Path(p).name.split("_", 1)[0] in ids)
    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"대상 PDF {len(pdfs)}개 스캔", file=sys.stderr)

    by_ntt: dict[str, dict] = {}
    for i, pp in enumerate(pdfs):
        nid = Path(pp).name.split("_", 1)[0]
        if nid in by_ntt:
            continue
        pages = find_approval_pages(pp)  # fast fitz prefilter
        if pages:
            try:
                with pdfplumber.open(pp) as doc:
                    for pidx in pages:  # 목차 page는 실패 → 실제 표 page까지 시도
                        r = extract_page(doc.pages[pidx], _repair_cid)
                        if r:
                            by_ntt[nid] = r
                            break
            except Exception:
                pass
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(pdfs)} — 국정평가 {len(by_ntt)}건", file=sys.stderr)

    records = []
    for nid, r in by_ntt.items():
        m = meta[nid]
        ps = m.get("survey_start", "") or parse_survey_period(m.get("survey_period", ""))[0]
        pe = m.get("survey_end", "") or parse_survey_period(m.get("survey_period", ""))[1]
        records.append({
            "ntt_id": nid, "agency": m.get("agency", ""),
            "period_start": ps, "period_end": pe,
            "sido": region_sido(m.get("region", "")),
            "subject": president_on(pe or ps),  # 조사일 기준 현직 대통령
            "positive": r["positive"], "negative": r["negative"],
            "source_url": m.get("source_url", ""),
        })
    records.sort(key=lambda x: x["period_end"] or "")
    print(f"국정평가 추출 {len(records)}건 (전국 {sum(1 for r in records if not r['sido'])})", file=sys.stderr)
    if args.dry_run:
        for r in records[-8:]:
            print(f"  {r['period_end']} {r['subject']} {r['sido'] or '전국':6} 긍정{r['positive']} 부정{r['negative']} ({r['agency'][:10]})", file=sys.stderr)
        return
    OUT.write_text(json.dumps({"_meta": {"metric": "대통령 국정수행 평가",
                   "n": len(records)}, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
