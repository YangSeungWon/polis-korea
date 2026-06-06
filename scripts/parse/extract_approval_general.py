"""범용 대통령 국정평가 추출 → data/polls/approval_general.json.

기관별 파서(갤럽·리얼미터·NBS·한국리서치)로 안 잡힌 전국 파일을 한 번에. 조원씨앤아이·
한길리서치·알앤써치·여론조사공정·리서치뷰·미디어토마토 등.

원리(기관 무관·컬럼순서 무관):
  '대통령 국정운영/수행 평가' 표의 '전체' 행 값들을 헤더 라벨로 긍정/부정/모름 분류,
  - 각 측 **집계값 = 나머지 성분 합** 이면 그 집계값 채택(아니면 성분 합).
  - **긍정 + 부정 + 모름 ≈ 100** 으로 표 검증(정당대표 직무·평가이유·투표의향 등 배제).
제목 exclude: 잘하는/잘못하는 점·신뢰·이유·대표(정당대표). subject=president_on(직무정지 제외).

사용: python3 scripts/parse/extract_approval_general.py [--limit N --debug]
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
import fitz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "parse"))
sys.path.insert(0, str(ROOT / "scripts" / "build"))
from parse_pdf_v2 import _repair_cid  # noqa: E402
from cid_decode import repair_text, needs_repair  # noqa: E402
from extract_approval import load_meta  # noqa: E402
from extract_approval_gallup import subject_for  # noqa: E402

OUT = ROOT / "data" / "polls" / "approval_general.json"
_JOB = re.compile(r"국정\s*운영|국정\s*수행|직무\s*수행|국정\s*지지")
# 제목에 있으면 직무평가 아님 — 잘하는/잘못하는 점·신뢰·평가이유·정당대표·지수,
# 정권심판/책임론·국정안정론, 전 대통령 회고/계엄·탄핵 평가, 후보 능력평가.
_TITLE_EXC = ("잘하는", "잘못하는", "신뢰", "이유", "대표", "지수",
              "책임", "심판", "차질", "안정론", "전대통령", "재임", "계엄", "회고",
              "능력", "후보", "물어야", "견제", "지원")
_VAL = re.compile(r"^\d{1,3}(?:\.\d+)?$")  # 0~100(.x), 괄호·콤마·4자리(사례수) 제외


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
            if _JOB.search(t) and "대통령" in t:
                out.append(i)
    finally:
        doc.close()
    return out


def _classify(label: str) -> str:
    """컬럼 라벨 → 'dk'/'neg'/'pos'/''. 순서 중요(모름·부정 먼저, 잘못은 잘 포함)."""
    if re.search(r"모름|무응답|유보|모르", label):
        return "dk"
    if re.search(r"부정|잘못|못하|매우못|③|④|B2", label):
        return "neg"
    if re.search(r"긍정|잘하|잘함|매우잘|①|②|T2", label):
        return "pos"
    return ""


def _agg_or_sum(vals: list[float]) -> float | None:
    """집계값(=나머지 합)이 있으면 그 값, 없으면 전체 합."""
    if not vals:
        return None
    tot = sum(vals)
    for v in vals:
        if abs(v - (tot - v)) < 1.2:   # v ≈ 나머지 합 → 집계열
            return round(v, 1)
    return round(tot, 1)


def extract_page(pg, debug=False) -> dict | None:
    rows = defaultdict(list)
    for w in pg.extract_words(x_tolerance=1.5):
        rows[round(w["top"] / 2) * 2].append(((w["x0"] + w["x1"]) / 2, _repair_cid(w["text"])))
    tops = sorted(rows)

    title_y = None
    for top in tops:
        line = "".join(t for _, t in sorted(rows[top]))
        h = re.sub(r"[^가-힣]", "", line)
        # 제목/질문 행: 국정운영/수행/지지 언급 (정당대표 직무·평가이유·잘하는점 등 배제).
        if _JOB.search(line) and not any(x in h for x in _TITLE_EXC):
            title_y = top
            break
    if title_y is None:
        return None

    for top in tops:
        if not (title_y < top < title_y + 130):
            continue
        ws = sorted(rows[top])
        lab0 = re.sub(r"[^가-힣]", "", "".join(t for _, t in ws))
        if not lab0.startswith("전체"):
            continue
        cols = [(xc, float(t)) for xc, t in ws if _VAL.match(t)]
        if len(cols) < 3:
            continue
        # 헤더 토큰을 가장 가까운 값-컬럼에 배정(분할 라벨 '못 하는 편' 등 그룹화).
        labels = ["" for _ in cols]
        col_xs = [xc for xc, _ in cols]
        for tt in tops:
            if not (title_y <= tt < top):
                continue
            for hx, htext in rows[tt]:
                if not re.search(r"[가-힣①②③④BT2]", htext):
                    continue
                ci = min(range(len(col_xs)), key=lambda k: abs(col_xs[k] - hx))
                if abs(col_xs[ci] - hx) <= 40:
                    labels[ci] += htext
        sides = {"pos": [], "neg": [], "dk": []}
        for (xc, val), label in zip(cols, labels):
            cl = _classify(re.sub(r"[^가-힣①②③④BT2]", "", label))
            if cl:
                sides[cl].append(val)
        pos = _agg_or_sum(sides["pos"])
        neg = _agg_or_sum(sides["neg"])
        dk = _agg_or_sum(sides["dk"]) or 0.0
        if debug:
            print(f"      전체 pos{sides['pos']}→{pos} neg{sides['neg']}→{neg} dk{dk}", file=sys.stderr)
        if pos and neg:
            ok = (sides["dk"] and 97 <= pos + neg + dk <= 103) or \
                 (not sides["dk"] and 80 <= pos + neg <= 100)
            if ok and 0 < pos < 100 and 0 < neg < 100:
                return {"positive": round(pos, 1), "negative": round(neg, 1)}
        return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="comma nids (테스트)")
    args = ap.parse_args()

    meta = load_meta()
    fmap = {}
    for f in os.listdir(ROOT / "data/raw/pdf"):
        if f.endswith(".pdf"):
            fmap.setdefault(f.split("_", 1)[0], f)
    captured = set()
    for s in ["gallup", "realmeter", "nbs", "hrc"]:
        p = ROOT / "data/polls" / f"approval_{s}.json"
        if p.exists():
            captured |= {r["ntt_id"] for r in json.loads(p.read_text())["records"]}

    def is_nat(m):
        r = (m.get("region") or "").strip()
        return (not r) or r.startswith("전국")
    if args.only:
        ids = args.only.split(",")
    else:
        ids = [nid for nid, m in meta.items()
               if is_nat(m) and nid in fmap and nid not in captured]
    pdfs = sorted(str(ROOT / "data/raw/pdf" / fmap[nid]) for nid in ids if nid in fmap)
    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"미캡처 전국 PDF {len(pdfs)}개 스캔", file=sys.stderr)

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
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(pdfs)} — {len(by_ntt)}건", file=sys.stderr)

    # 4기관(검증완료) 월별 긍정 평균 — 독립 측정 consensus로 이상치 컷.
    consensus = defaultdict(list)
    for s in ["gallup", "realmeter", "nbs", "hrc"]:
        p = ROOT / "data/polls" / f"approval_{s}.json"
        if p.exists():
            for rr in json.loads(p.read_text())["records"]:
                consensus[(rr["subject"], rr["period_end"][:7])].append(rr["positive"])
    cmean = {k: sum(v) / len(v) for k, v in consensus.items()}

    records, dropped = [], 0
    for nid, r in by_ntt.items():
        m = meta[nid]
        ps = m.get("survey_start", "") or ""
        pe = m.get("survey_end", "") or ps
        subj = subject_for(pe or ps)
        if not subj:
            continue
        # consensus 교차검증 — 같은 달 4기관 평균과 20%p 이상 벌어지면 오독으로 컷.
        ref = cmean.get((subj, (pe or ps)[:7]))
        if ref is not None and abs(r["positive"] - ref) > 20:
            dropped += 1
            if args.debug:
                print(f"  DROP {nid} {pe} {subj} {r['positive']} vs 합의 {ref:.0f}", file=sys.stderr)
            continue
        records.append({
            "ntt_id": nid, "agency": m.get("agency", ""),
            "period_start": ps, "period_end": pe,
            "subject": subj, "positive": r["positive"], "negative": r["negative"],
            "source_url": m.get("source_url", ""),
        })
    records.sort(key=lambda x: x["period_end"] or "")
    if dropped:
        print(f"consensus 컷 {dropped}건", file=sys.stderr)
    print(f"범용 국정평가 {len(records)}건", file=sys.stderr)
    if args.dry_run or args.debug:
        from collections import Counter
        print("subject:", Counter(r["subject"] for r in records), file=sys.stderr)
        if not args.only:
            return
    OUT.write_text(json.dumps({"_meta": {"metric": "대통령 국정평가 (범용·기타 기관)",
                   "n": len(records)}, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
