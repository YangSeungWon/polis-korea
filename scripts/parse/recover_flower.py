"""여론조사꽃류 괘선없는 cross-tab 결과표 복구 → parsed JSON 재기록.

문제: 여론조사꽃 결과표는 ruling line이 없어 pdfplumber `extract_tables`가 인접 숫자 컬럼을
병합("36.042.70.41")하고 후보명을 라벨에 묻어버림 → parse_pdf_v2 실패. 단, `extract_words`로
뽑으면 단어 x좌표는 멀쩡하고 cid도 정상 복구됨(parse_pdf_v2._repair_cid).

복구법: 단어를 x로 컬럼 클러스터링(다줄 헤더 "더불어"+"민주당"→"더불어민주당" 결합) →
'전체' 데이터행의 pct를 컬럼 x에 nearest 정렬 → roster 후보명/정당명으로 컬럼 식별.

election_office:
  - 컬럼에 선거구 roster 후보명 있으면 → 후보지지 (name=후보, party=roster/같은컬럼 정당)
  - title에 '비례' + 정당 컬럼 → 비례정당
  - 그 외 정당 컬럼 → 정당지지

build_polls_gen.py가 그대로 집어가도록 해당 PDF의 parsed JSON을 덮어씀.

사용:
  python3 scripts/parse/recover_flower.py --election 22nd-general-2024 [--dry-run] [--limit N]
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "parse"))
sys.path.insert(0, str(ROOT / "scripts" / "build"))
from parse_pdf_v2 import _repair_cid  # cid 복구 (이미 검증됨)  # noqa: E402

PARSED_DIR = ROOT / "data" / "raw" / "parsed"

SIDO_SHORT = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}

# 컬럼 라벨이 이것들이면 후보/정당 아님 (메트릭 컬럼)
NON_DATA_COL = re.compile(r"전체|조사|완료|사례|단위|모름|무응답|없[음다]|가중|적용|Base|소계|합계|기타")
_PCT = re.compile(r"^\d{1,3}\.\d$")
_PAREN = re.compile(r"^\(.*\)$")


def load_meta(csv_path: Path) -> dict[str, dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {r["ntt_id"]: r for r in csv.DictReader(f)}


def region_to_district(region: str) -> str:
    if not region or region.startswith("전국"):
        return ""
    region = region.replace("서울틀별시", "서울특별시")
    toks = [t for t in region.split() if t not in ("선거구", "전체", "전지역", "전 지역")]
    if not toks:
        return ""
    sido = SIDO_SHORT.get(toks[0], toks[0])
    vals = set(SIDO_SHORT.values())
    body = [t for t in toks[1:] if SIDO_SHORT.get(t, t) not in vals]
    dd = []
    for t in body:
        if not dd or dd[-1] != t:
            dd.append(t)
    out: list[str] = []
    for t in dd:
        m = re.match(r"^(.*?)([갑을병정])$", t)
        if m and out and m.group(1) and (out[-1].startswith(m.group(1)) or m.group(1) in out[-1]):
            out[-1] = out[-1] + m.group(2)
        else:
            out.append(t)
    return f"{sido}|{''.join(out)}"


def _rows(pg) -> dict:
    """top(3px bin) → [{x0,x1,xc,t}]."""
    rows: dict = {}
    for w in pg.extract_words(x_tolerance=1.5):
        t = _repair_cid(w["text"]).strip()
        if not t:
            continue
        rows.setdefault(round(w["top"] / 3) * 3, []).append(
            {"x0": w["x0"], "x1": w["x1"], "xc": (w["x0"] + w["x1"]) / 2, "t": t})
    return rows


def _cluster_columns(header_words: list[dict], tol: float = 16) -> list[dict]:
    """헤더 단어를 x로 컬럼 클러스터링 → [{xc, label}] (다줄 라벨 결합)."""
    cols: list[dict] = []
    for w in sorted(header_words, key=lambda w: w["xc"]):
        for c in cols:
            if abs(c["xc"] - w["xc"]) <= tol:
                c["words"].append(w)
                c["xc"] = sum(x["xc"] for x in c["words"]) / len(c["words"])
                break
        else:
            cols.append({"xc": w["xc"], "words": [w]})
    for c in cols:
        # top 순으로 라벨 결합
        c["label"] = "".join(x["t"] for x in sorted(c["words"], key=lambda x: x.get("top", 0)))
    return cols


def recover_page(rows: dict, roster_dist: dict, parties: set) -> dict | None:
    """한 page의 result table 복구 → {election_office, title, candidates} 또는 None."""
    tops = sorted(rows)
    # '전체' 데이터행 찾기 (첫 토큰 '전체' + pct ≥2)
    total_top = None
    pcts: list[tuple[float, float]] = []
    for top in tops:
        ws = sorted(rows[top], key=lambda w: w["x0"])
        if ws and ws[0]["t"] == "전체":
            cand = [(float(w["t"]), w["xc"]) for w in ws[1:] if _PCT.match(w["t"])]
            if len(cand) >= 2:
                total_top, pcts = top, cand
                break
    if total_top is None:
        return None
    # 헤더 band = 전체행 위 ~90px 안의 단어 (title 줄 제외 위해 pct/숫자 only 줄은 무시)
    header_words = []
    for top in tops:
        if not (total_top - 90 <= top < total_top):
            continue
        for w in rows[top]:
            if _PCT.match(w["t"]) or _PAREN.match(w["t"]):
                continue
            w2 = dict(w); w2["top"] = top
            header_words.append(w2)
    cols = _cluster_columns(header_words)
    # 각 컬럼을 nearest pct에 정렬
    out_cands = []
    used = set()
    for c in cols:
        if NON_DATA_COL.search(c["label"]):
            continue
        # roster 후보명 or 정당명 추출
        name = next((nm for nm in roster_dist if nm in c["label"]), "")
        party = next((p for p in parties if p in c["label"]), "")
        if not name and not party:
            continue
        # nearest pct (미사용 우선)
        best = min(((i, p) for i, p in enumerate(pcts) if i not in used),
                   key=lambda ip: abs(ip[1][1] - c["xc"]), default=None)
        if best is None:
            continue
        i, (pct, _) = best
        used.add(i)
        if name:
            out_cands.append({"name": name, "party": party or roster_dist.get(name, ""), "pct": pct})
        else:
            out_cands.append({"name": "", "party": party, "pct": pct})
    if len(out_cands) < 2:
        return None
    # election_office 분류 + 표준 title (원본 title은 "현안" 등 build reject 키워드 포함해
    # 깨끗한 canonical로 대체 — roster/정당 매칭이 이미 검증 역할).
    has_cand = any(c["name"] for c in out_cands)
    title_words = " ".join(t["t"] for top in tops[:6] for t in rows[top])
    if has_cand:
        eo, title = "후보지지", "지역구 후보 지지도"
    elif "비례" in title_words:
        eo, title = "비례정당", "비례대표 정당투표"
    else:
        eo, title = "정당지지", "정당 지지도"
    return {"election_office": eo, "title": title, "candidates": out_cands}


def recover_pdf(pdf_path: Path, roster_dist: dict, parties: set) -> list[dict]:
    qs = []
    try:
        with pdfplumber.open(pdf_path) as doc:
            for pg in doc.pages:
                q = recover_page(_rows(pg), roster_dist, parties)
                if q:
                    qs.append(q)
    except Exception as e:
        print(f"  ! {pdf_path.name}: {e}", file=sys.stderr)
    return qs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--election", default="22nd-general-2024")
    ap.add_argument("--csv", default="data/raw/nesdc_22gen_polls.csv")
    ap.add_argument("--agency", default="여론조사꽃", help="대상 조사기관 키워드")
    ap.add_argument("--roster", default="data/raw/nec_roster_22gen.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    meta = load_meta(ROOT / args.csv)
    roster = json.loads((ROOT / args.roster).read_text(encoding="utf-8"))
    districts = roster["districts"]
    parties = set(roster["proportional_parties"]) | {
        "더불어민주당", "국민의힘", "조국혁신당", "개혁신당", "녹색정의당",
        "새로운미래", "진보당", "자유통일당", "기본소득당"}

    targets = [(nid, m) for nid, m in meta.items() if args.agency in m.get("agency", "")]
    if args.limit:
        targets = targets[:args.limit]
    print(f"대상 {args.agency}: {len(targets)} ntt", file=sys.stderr)

    n_patched = n_q = 0
    by_eo: dict = {}
    for nid, m in targets:
        rd = districts.get(region_to_district(m.get("region", "")), {})
        pdfs = sorted((ROOT / "data/raw/pdf").glob(f"{nid}_*.pdf"))
        best_qs: list[dict] = []
        for pdf in pdfs:
            qs = recover_pdf(pdf, rd, parties)
            if len(qs) > len(best_qs):
                best_qs, best_pdf = qs, pdf
        if not best_qs:
            continue
        for q in best_qs:
            by_eo[q["election_office"]] = by_eo.get(q["election_office"], 0) + 1
        n_patched += 1; n_q += len(best_qs)
        if not args.dry_run:
            out = {"source_pdf": best_pdf.name, "ntt_id": nid, "questions": best_qs}
            (PARSED_DIR / (best_pdf.stem + ".json")).write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"복구: {n_patched} ntt, {n_q} questions {by_eo}", file=sys.stderr)
    if args.dry_run:
        print("[dry-run] parsed JSON 미기록", file=sys.stderr)


if __name__ == "__main__":
    main()
