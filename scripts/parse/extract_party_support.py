"""VT012('기타') 전국 정기 정당지지도 추출 → data/polls/aggregated_etc.json.

선거 무관 연속 트래킹(갤럽·리얼미터·NBS 등 주간/격주 정당지지)이 VT012로 등록됨.
build_polls_*(선거별)로는 안 들어오므로 직접 추출 — '정당 지지도' 표 '전체' 행의
정당명 컬럼별 % 를 매핑. aggregated_*.json과 같은 shape(polls list)이라 tracker가 그대로 읽음.

추출: 전체 행 값 컬럼 → 최근접 헤더 라벨 → PARTY_NAMES 최장일치 = 그 정당. 비-정당(없음/모름)
무시. 양대(민주계+국힘계) 동시 출현 + 합≈100 검증(비례·후보지지·하위질문 배제).

사용: python3 scripts/parse/extract_party_support.py [--limit N --debug]
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
import fitz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "parse"))
from parse_pdf_v2 import _repair_cid  # noqa: E402
from cid_decode import repair_text, needs_repair  # noqa: E402
from poll_terms import PARTY_NAMES  # noqa: E402

CSV = ROOT / "data" / "raw" / "nesdc_etc_polls.csv"
OUT = ROOT / "data" / "polls" / "aggregated_etc.json"
_TITLE = re.compile(r"정당\s*지지|지지.{0,2}정당|어느\s*정당")
_TITLE_EXC = ("비례", "후보", "대선", "추이", "차기")
_VAL = re.compile(r"^\d{1,3}(?:\.\d+)?$")
# 양대 계열 — 둘 다 있어야 진짜 정당지지표
DEM = {"더불어민주당", "민주당", "더불어시민당", "새정치민주연합", "민주통합당"}
PPP = {"국민의힘", "국힘", "미래통합당", "자유한국당", "새누리당", "미래한국당", "국민의미래"}
# 헤더 라벨에서 정당 매칭 — 긴 이름 우선
_PARTIES = sorted(set(PARTY_NAMES) | DEM | PPP, key=len, reverse=True)
NON_PARTY_TOK = ("없음", "모름", "무응답", "기타", "다른", "유보", "지지정당")


def match_party(label: str) -> str | None:
    h = re.sub(r"[^가-힣]", "", label)
    if not h or any(x in h for x in NON_PARTY_TOK):
        return None
    for p in _PARTIES:
        if p in h:
            return p
    return None


def load_meta() -> dict:
    if not CSV.exists():
        return {}
    return {r["ntt_id"]: r for r in csv.DictReader(open(CSV, encoding="utf-8"))}


def find_party_pages(pp: str) -> list[int]:
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
            if _TITLE.search(t) and "민주" in t:
                out.append(i)
    finally:
        doc.close()
    return out


def extract_page(pg, debug=False) -> list | None:
    rows = defaultdict(list)
    for w in pg.extract_words(x_tolerance=1.5):
        rows[round(w["top"] / 2) * 2].append(((w["x0"] + w["x1"]) / 2, _repair_cid(w["text"])))
    tops = sorted(rows)

    title_y = None
    for top in tops:
        line = "".join(t for _, t in sorted(rows[top]))
        h = re.sub(r"[^가-힣]", "", line)
        if _TITLE.search(line) and not any(x in h for x in _TITLE_EXC):
            title_y = top
            break
    if title_y is None:
        return None

    for top in tops:
        if not (title_y < top < title_y + 130):
            continue
        ws = sorted(rows[top])
        lab = re.sub(r"[^가-힣]", "", "".join(t for _, t in ws))
        if not lab.startswith("전체"):
            continue
        cols = [(xc, float(t)) for xc, t in ws if _VAL.match(t)]
        if len(cols) < 3:
            continue
        labels = ["" for _ in cols]
        col_xs = [xc for xc, _ in cols]
        for tt in tops:
            if not (title_y <= tt < top):
                continue
            for hx, htext in rows[tt]:
                if not re.search(r"[가-힣]", htext):
                    continue
                ci = min(range(len(col_xs)), key=lambda k: abs(col_xs[k] - hx))
                if abs(col_xs[ci] - hx) <= 40:
                    labels[ci] += htext
        cands = []
        for (xc, val), label in zip(cols, labels):
            party = match_party(label)
            if party and val >= 0:
                cands.append({"name": "", "party": party, "pct": val})
        res = _validate(cands, debug, "열")
        if res:
            return res
        # 검증 실패 → 다음 '전체' 행 시도(전치 레이아웃은 cross-tab 오독 위험으로 미사용).
    return None


def _validate(cands, debug, mode):
    parties = {c["party"] for c in cands}
    psum = sum(c["pct"] for c in cands)
    if debug:
        print(f"      [{mode}] {[(c['party'],c['pct']) for c in cands]} 합{psum:.0f}", file=sys.stderr)
    if (parties & DEM) and (parties & PPP) and len(cands) >= 2 and 20 <= psum <= 102:
        best = {}
        for c in cands:
            if c["party"] not in best or c["pct"] > best[c["party"]]["pct"]:
                best[c["party"]] = c
        return list(best.values())
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--only")
    args = ap.parse_args()

    meta = load_meta()
    def is_nat(m):
        r = (m.get("region") or "").strip()
        return (not r) or r.startswith("전국")
    if args.only:
        ids = args.only.split(",")
    else:
        ids = [nid for nid, m in meta.items() if is_nat(m)]
    fmap = {}
    for f in glob.glob(str(ROOT / "data/raw/pdf/*.pdf")):
        fmap.setdefault(Path(f).name.split("_", 1)[0], f)
    pdfs = [fmap[nid] for nid in ids if nid in fmap]
    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"VT012 전국 PDF {len(pdfs)}개 스캔", file=sys.stderr)

    polls = []
    seen = set()
    for i, pp in enumerate(pdfs):
        nid = Path(pp).name.split("_", 1)[0]
        if nid in seen:
            continue
        pages = find_party_pages(pp)
        if not pages:
            continue
        try:
            with pdfplumber.open(pp) as doc:
                for pidx in pages:
                    cands = extract_page(doc.pages[pidx], debug=args.debug)
                    if cands:
                        m = meta[nid]
                        polls.append({
                            "ntt_id": nid, "source_url": m.get("source_url", ""),
                            "agency": m.get("agency", ""), "period_start": m.get("survey_start", ""),
                            "period_end": m.get("survey_end", "") or m.get("survey_start", ""),
                            "sido": "", "sigungu": "", "office_level": "정당지지",
                            "office_label": "정당지지", "metric_type": "정당지지",
                            "table_title": "정당 지지도", "candidates": cands,
                        })
                        seen.add(nid)
                        if args.debug:
                            print(f"  {nid} → {[(c['party'],c['pct']) for c in cands]}", file=sys.stderr)
                        break
        except Exception as e:
            if args.debug:
                print(f"  {nid} ERR {e}", file=sys.stderr)
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(pdfs)} — {len(polls)}건", file=sys.stderr)

    polls.sort(key=lambda p: p["period_end"] or "")
    print(f"VT012 정당지지 {len(polls)}건", file=sys.stderr)
    if args.debug and not args.only:
        return
    OUT.write_text(json.dumps({"_meta": {"source": "VT012 기타 전국 정기 정당지지", "n": len(polls)},
                   "polls": polls}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
