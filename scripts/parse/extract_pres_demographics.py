#!/usr/bin/env python3
"""대선 전국 여론조사 PDF의 '응답자 특성별 후보지지도' cross-tab → 성×연령 추출.

NESDC 통계표(결과분석)는 후보지지도를 응답자 특성별로 교차분석한다:
  전체 / 성별(남·여) / 연령(전체) / 남성×연령 / 여성×연령 / 권역 / 정당지지도별 ...
각 행 = [섹션] [행라벨] (사례수1) (사례수2) pct1 pct2 ... (열=후보, extract_pres_region과 동일).

이 도구는 그 표에서 성별·연령·성×연령(그리드) 행을 뽑는다. 이대남/이대녀 분석의 데이터.
best-effort(표준 NESDC 결과분석 포맷). 레이아웃 다른 기관은 미추출(coverage 리포트).

출력: data/raw/parsed/pres_demographics_<id>.json =
  { ntt_id: { "성별": {남성:[cand], 여성:[cand]},
              "연령": {"18-29":[cand], "30":[cand], ...},
              "성연령": {"남성": {"18-29":[cand],...}, "여성": {...}} } }
"""
from __future__ import annotations
import csv
import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cid_decode import build_cid_table  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW_PDF = ROOT / "data/raw/pdf"
PARSED = ROOT / "data/raw/parsed"
PAGE_CAP = 22

_CID_RE = re.compile(r"\(cid:(\d+)\)")
_CID_TABLE = None


def decode(s: str) -> str:
    global _CID_TABLE
    if "(cid:" not in s:
        return s
    if _CID_TABLE is None:
        _CID_TABLE = build_cid_table()
    return _CID_RE.sub(lambda m: _CID_TABLE.get(int(m.group(1)), ""), s)


# 연령 라벨 정규화 — 기관별 표기 변종 흡수.
def norm_age(lab: str):
    s = lab.replace(" ", "")
    if re.search(r"(18|19|20)[/~\-]?(20대|29)|^20대|만18|18세|18/20", s):
        return "18-29"
    if "30대" in s or re.search(r"^30", s):
        return "30"
    if "40대" in s or re.search(r"^40", s):
        return "40"
    if "50대" in s or re.search(r"^50", s):
        return "50"
    if "60대" in s or re.search(r"60세이상", s):
        return "60" if "이상" not in s else "60+"
    if re.search(r"70대|70세이상|70\+|만70", s):
        return "70+"
    return None


def find_crosstab(doc, names: list[str]):
    need = [c for c in names if c][:5]
    for pg in doc.pages[:PAGE_CAP]:
        t = decode(pg.extract_text() or "")
        lines = t.split("\n")
        hdr = next((i for i, ln in enumerate(lines[:14])
                    if sum(c in ln for c in need) >= max(2, len(need) - 1)), None)
        if hdr is None:
            continue
        # 성별/연령 행 둘 다 보여야 특성별 표
        body = "\n".join(lines)
        if ("남" in body and "여" in body) and re.search(r"(18[/~\-]?20|20대|30대|40대|50대|60대)", body):
            return lines, hdr
    return None, None


def cand_order(header: str, names: list[str]) -> list[str]:
    pos = [(header.find(c), c) for c in names if c and c in header]
    return [c for _, c in sorted(pos)]


def row_pcts(ln: str, n: int):
    """행에서 후보 N개 pct(소수) 추출. 앞쪽 정수(사례수)는 건너뜀."""
    floats = re.findall(r"\d+\.\d+", ln)
    return [float(x) for x in floats[:n]] if len(floats) >= n else None


def parse_pdf(pdf_path: Path, cands: list[dict]):
    names = [c.get("name") for c in cands if c.get("name")]
    party = {c.get("name"): c.get("party", "") for c in cands}
    try:
        with pdfplumber.open(pdf_path) as doc:
            lines, hdr = find_crosstab(doc, names)
    except Exception:
        return None
    if not lines:
        return None
    order = cand_order(lines[hdr], names)
    if len(order) < 2:
        return None
    N = len(order)

    def cand_row(pcts):
        return [{"name": order[i], "party": party.get(order[i], ""), "pct": pcts[i]} for i in range(N)]

    out = {"성별": {}, "연령": {}, "성연령": {"남성": {}, "여성": {}}}
    # pdfplumber extract_text는 병합 좌측라벨(성별/연령/남성/여성)을 블록 중간·뒤에 토함 → 라벨위치 신뢰 불가.
    #   구조로 귀속: 성별(남/여 행) + 연령블록 순서 [연령전체, 남성×연령, 여성×연령](NEC 표준).
    #   연령이 18-29(최연소)로 리셋될 때마다 새 블록.
    STOP = re.compile(r"권\s*역|지\s*역|정당\s*지지|이념|직\s*업|규\s*모|학\s*력|지지\s*후보|적\s*합|후보\s*적합")
    male = re.compile(r"^(성\s*별)?\s*(남\s*성|남\s*자)\b")
    female = re.compile(r"^(성\s*별)?\s*(여\s*성|여\s*자)\b")
    age_blocks = []
    cur_block = None
    started = False

    for ln in lines[hdr + 1:]:
        flat = ln.replace(" ", "")
        if not flat:
            continue
        age = norm_age(flat)
        pcts = row_pcts(ln, N)
        is_m, is_f = bool(male.match(ln)), bool(female.match(ln))
        if STOP.search(ln) and not age:
            if started:
                break
            continue
        # 성별 단독 행 (남/여 + pct, 연령 없음)
        if (is_m or is_f) and pcts and not age:
            out["성별"].setdefault("남성" if is_m else "여성", cand_row(pcts))
            started = True
            continue
        # 연령 행 — 블록 단위 수집(18-29 재등장 = 새 블록)
        if age and pcts:
            if cur_block is None or (age == "18-29" and "18-29" in cur_block):
                cur_block = {}
                age_blocks.append(cur_block)
            cur_block[age] = cand_row(pcts)
            started = True

    # 블록 귀속 — [0]=연령 overall, [1]=남성, [2]=여성 (NEC 표준 순서)
    if len(age_blocks) >= 1:
        out["연령"] = age_blocks[0]
    if len(age_blocks) >= 3:
        out["성연령"]["남성"] = age_blocks[1]
        out["성연령"]["여성"] = age_blocks[2]

    if out["성별"] or out["연령"] or out["성연령"]["남성"] or out["성연령"]["여성"]:
        return out
    return None


def main():
    if len(sys.argv) < 2:
        print("usage: extract_pres_demographics.py <election_id>  (예: 21st-pres-2025)", file=sys.stderr)
        sys.exit(2)
    eid = sys.argv[1]
    short = eid.split("-")[0]
    for sfx in ("th", "st", "nd", "rd"):
        short = short.replace(sfx, "")
    csv_path = ROOT / f"data/raw/nesdc_{short}pres_polls.csv"
    meta = {}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            meta[row["ntt_id"]] = row
    meta_ids = set(meta)
    parsed_cand = {}
    for p in PARSED.glob("*.json"):
        if p.name.split("_")[0] not in meta_ids:
            continue
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        ntt = str(d.get("ntt_id") or p.name.split("_")[0])
        for q in d.get("questions", []):
            if q.get("election_office") == "후보지지" and (q.get("candidates") or []):
                if ntt not in parsed_cand or len(q["candidates"]) > len(parsed_cand[ntt][1]):
                    parsed_cand[ntt] = (p, q["candidates"])

    cache_path = PARSED / ".pres_demo_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    out = {}
    ok = 0
    todo = list(parsed_cand.items())
    print(f"후보지지 parsed {len(todo)}건 — 특성별 cross-tab 스캔...", flush=True)
    for i, (ntt, (pj, cands)) in enumerate(todo):
        stem = pj.name[:-5]
        if stem in cache:
            rows = cache[stem]
        else:
            pdfs = list(RAW_PDF.glob(stem + ".*"))
            rows = parse_pdf(pdfs[0], cands) if pdfs else None
            cache[stem] = rows
        if rows:
            out[ntt] = rows
            ok += 1
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(todo)}, 추출 {ok}", flush=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    dst = PARSED / f"pres_demographics_{short}pres.json"
    dst.write_text(json.dumps(out, ensure_ascii=False))
    # 커버리지 요약
    g = sum(1 for v in out.values() if v.get("성연령", {}).get("남성"))
    print(f"{eid}: {len(todo)}건 중 특성별 추출 {ok}건 (성×연령 그리드 {g}건) → {dst.name}")


if __name__ == "__main__":
    main()
