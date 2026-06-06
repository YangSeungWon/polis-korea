"""한국갤럽 대통령 직무수행 평가(국정 지지율) 타깃 추출 → data/polls/approval_gallup.json.

일반 extract_approval은 PDF당 직무평가 표가 여러 개(현재·추이·역대비교·계층별)라
엉뚱한 표를 잡아 오류율 38%였다. 갤럽은 포맷이 일관되므로 **갤럽 전용**으로 정밀 추출한다.

갤럽 데일리 오피니언 주간 '정당지지도 결과분석' PDF에는 상세결과 집계표가 있고,
계층별 표의 **'전체' 행**이 그 주의 전국 직무평가다:
  전체  …  잘하고있다(긍정)  잘못하고있다(부정)  어느쪽도아니다  모름/응답거절
  예) 전체 … 47%  43%  5%  5%  (= 100)
→ 헤더 4컬럼 x중심을 잡고 '전체' 행 %를 정렬, 4성분 합이 ≈100인지로 검증(엉뚱한 표 배제).
subject = 조사일 기준 현직 대통령(president_on). 단, 직무정지(탄핵소추~파면/기각) 기간 제외
— 그 기간엔 갤럽이 직무평가를 묻지 않으므로 잡히는 4성분 표는 다른 질문이다.

사용:
  python3 scripts/parse/extract_approval_gallup.py            # 갤럽 전국 전수
  python3 scripts/parse/extract_approval_gallup.py --limit 30 --debug
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
import fitz  # pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "parse"))
sys.path.insert(0, str(ROOT / "scripts" / "build"))
from parse_pdf_v2 import _repair_cid  # noqa: E402
from cid_decode import repair_text, needs_repair  # noqa: E402
from extract_approval import load_meta, president_on, PRESIDENT_TERMS  # noqa: E402

OUT = ROOT / "data" / "polls" / "approval_gallup.json"

# 직무정지(탄핵소추 의결~파면/기각) 기간 — 현직이지만 직무평가 미실시. subject 무효.
SUSPENDED = [
    ("2016-12-09", "2017-03-10"),  # 박근혜 탄핵소추~파면
    ("2024-12-14", "2025-04-04"),  # 윤석열 탄핵소추~파면
]


def subject_for(date: str) -> str:
    for a, b in SUSPENDED:
        if a <= date <= b:
            return ""
    return president_on(date)


# 직무평가 표 키워드 — 이 표제 근처여야 직무평가 집계표로 인정.
_JOB_TITLE = re.compile(r"직무\s*수행\s*평가")
_PCT = re.compile(r"^(\d{1,3})%$")
_POS = "잘하고"      # 잘하고 있다 (직무 긍정률)
_NEG = "잘못하고"    # 잘못하고 있다 (부정률)
_ETC = "어느"        # 어느 쪽도 아니다
_DK = "모름"         # 모름/응답거절


def _han(t: str) -> str:
    return re.sub(r"[^가-힣/]", "", t)


def find_job_pages(pp: str) -> list[int]:
    """fitz로 '직무 수행 평가' 들어간 page index 전부."""
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
            if _JOB_TITLE.search(t):
                out.append(i)
    finally:
        doc.close()
    return out


_YEAR = re.compile(r"(20\d\d)\s*년")
_MON = re.compile(r"(\d{1,2})\s*월")


def _table_month(rows, before_y):
    """'전체' 행 위 타이틀 영역의 (year, month). 월별통합 doc은 page당 한 달이라
    엉뚱한 달 표를 잡지 않게 report 기간과 대조하는 키."""
    year = month = None
    for top in sorted(rows):
        if top >= before_y:
            break
        line = "".join(t for _, _, t in sorted(rows[top]))
        y = _YEAR.search(line)
        if y:
            year = int(y.group(1))
        mons = _MON.findall(line)
        if mons:
            month = int(mons[-1])
    return (year, month) if (year and month and 1 <= month <= 12) else None


def page_candidates(pg, debug=False) -> list:
    """이 page의 모든 유효 '전체' 직무 표 → [(ym, pos, neg)]. ym=(year,month) or None.
    한 PDF에 월별 통합 표가 여러 개라 caller가 report 달과 대조해 고른다."""
    rows: dict = defaultdict(list)
    for w in pg.extract_words(x_tolerance=1.5):
        rows[round(w["top"] / 2) * 2].append((w["x0"], (w["x0"] + w["x1"]) / 2, _repair_cid(w["text"])))
    tops = sorted(rows)

    # 헤더 행 후보 (Format A): 한 행에 잘하고+잘못하고+(어느 or 모름). prose는 어느/모름 없어 걸러짐.
    headers = []
    for top in tops:
        cols = {"pos": None, "neg": None, "etc": None, "dk": None}
        for _, xc, t in rows[top]:
            h = _han(t)
            for key, kw in (("pos", _POS), ("neg", _NEG), ("etc", _ETC), ("dk", _DK)):
                if h.startswith(kw) and cols[key] is None:
                    cols[key] = xc
                    break
        if cols["pos"] is not None and cols["neg"] is not None and (cols["etc"] or cols["dk"]):
            headers.append(cols)

    out = []
    for i, top in enumerate(tops):
        ws = sorted(rows[top])
        joined = "".join(t for _, _, t in ws)
        if not re.sub(r"[^가-힣]", "", joined).startswith("전체"):
            continue
        pcts = [(xc, float(m.group(1))) for _, xc, t in ws if (m := _PCT.match(t))]
        ym = _table_month(rows, top)
        res = None

        # Format A (~2024): 4컬럼(긍/부/어느/모름) 헤더 정렬, 합≈100.
        if headers and len(pcts) >= 2:
            def near(cx):
                return min(pcts, key=lambda p: abs(p[0] - cx))
            for hd in headers:
                pp_, np_ = near(hd["pos"]), near(hd["neg"])
                if pp_[0] == np_[0]:
                    continue
                pos, neg = pp_[1], np_[1]
                total = pos + neg + (near(hd["etc"])[1] if hd["etc"] else 0) \
                    + (near(hd["dk"])[1] if hd["dk"] else 0)
                if 96 <= total <= 104 and pos > 0 and neg > 0:
                    res = (pos, neg)
                    break

        # Format B (2025+): 어느쪽도/모름 없이 행마다 잘하고있다/잘못하고있다 + 점추정·CI.
        # '전체' 잘하고있다 행의 최좌측 정수%=점추정, 다음 잘못하고있다 행도 동일.
        if res is None and _POS in joined and pcts:
            pos = min(pcts, key=lambda p: p[0])[1]
            neg = None
            for top2 in tops[i + 1:i + 4]:
                ws2 = sorted(rows[top2])
                if _NEG in "".join(t for _, _, t in ws2):
                    np2 = [(xc, float(m.group(1))) for _, xc, t in ws2 if (m := _PCT.match(t))]
                    if np2:
                        neg = min(np2, key=lambda p: p[0])[1]
                    break
            if neg and 70 <= pos + neg <= 100:
                res = (pos, neg)

        if res:
            out.append((ym, round(res[0], 1), round(res[1], 1)))
            if debug:
                print(f"      cand y{top} ym{ym}: pos{res[0]} neg{res[1]}", file=sys.stderr)
    return out


def extract_gallup(pp, target_ym, debug=False) -> dict | None:
    """report 달(target_ym)과 일치하는 '전체' 직무 표 채택 (월별통합 doc 대비)."""
    cands = []
    try:
        with pdfplumber.open(pp) as doc:
            for pidx in find_job_pages(pp):
                cands += page_candidates(doc.pages[pidx], debug)
    except Exception as e:
        if debug:
            print(f"    ERR {e}", file=sys.stderr)
        return None
    if not cands:
        return None
    # 1) (year,month) 정확 매치
    exact = [c for c in cands if c[0] == target_ym]
    chosen = None
    if exact:
        chosen = exact[0]
    elif target_ym:
        ty, tm = target_ym
        dated = [c for c in cands if c[0]]
        same = [c for c in dated if c[0][0] == ty]
        pool = same or dated
        if pool:
            chosen = min(pool, key=lambda c: abs((c[0][0] * 12 + c[0][1]) - (ty * 12 + tm)))
    if chosen is None:
        chosen = cands[0]
    return {"positive": chosen[1], "negative": chosen[2]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    meta = load_meta()
    # 갤럽 전국 PDF만
    def is_nat(m):
        r = (m.get("region") or "").strip()
        return (not r) or r.startswith("전국")
    gallup_ids = {nid for nid, m in meta.items()
                  if "갤럽" in (m.get("agency") or "") and is_nat(m)}
    pdfs = sorted(p for p in glob.glob(str(ROOT / "data/raw/pdf/*.pdf"))
                  if Path(p).name.split("_", 1)[0] in gallup_ids)
    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"갤럽 전국 PDF {len(pdfs)}개 스캔", file=sys.stderr)

    by_ntt: dict[str, dict] = {}
    for i, pp in enumerate(pdfs):
        nid = Path(pp).name.split("_", 1)[0]
        if nid in by_ntt:
            continue
        m = meta[nid]
        pe = (m.get("survey_end") or m.get("survey_start") or "")
        target_ym = (int(pe[:4]), int(pe[5:7])) if len(pe) >= 7 and pe[:4].isdigit() else None
        if args.debug:
            print(f"--- {nid} ym{target_ym} {Path(pp).name[:50]}", file=sys.stderr)
        r = extract_gallup(pp, target_ym, debug=args.debug)
        if r:
            by_ntt[nid] = r
            if args.debug:
                print(f"    → {r}", file=sys.stderr)
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(pdfs)} — {len(by_ntt)}건", file=sys.stderr)

    records = []
    for nid, r in by_ntt.items():
        m = meta[nid]
        ps = m.get("survey_start", "") or ""
        pe = m.get("survey_end", "") or ps
        subj = subject_for(pe or ps)
        if not subj:
            continue  # 직무정지 기간 등 — 무효
        records.append({
            "ntt_id": nid, "agency": m.get("agency", ""),
            "period_start": ps, "period_end": pe,
            "subject": subj, "positive": r["positive"], "negative": r["negative"],
            "source_url": m.get("source_url", ""),
        })
    records.sort(key=lambda x: x["period_end"] or "")
    print(f"갤럽 직무평가 {len(records)}건", file=sys.stderr)
    if args.dry_run or args.debug:
        from collections import Counter
        print("subject:", Counter(r["subject"] for r in records), file=sys.stderr)
        return
    OUT.write_text(json.dumps({"_meta": {"metric": "대통령 직무수행 평가 (한국갤럽)",
                   "n": len(records)}, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
