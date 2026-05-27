"""표 선 없는 텍스트 PDF용 word-좌표 추출기 (OCR 불필요).

image_no_table로 분류됐지만 실제론 텍스트층이 멀쩡하고 표 격자선만 없는 PDF
(extract_tables=0이지만 extract_words는 정상). 퍼센트·이름·정당이 모두 읽히므로
pdfplumber word 좌표로 "전체" 행 값과 헤더(후보명/정당명)를 x별로 정렬해 추출.
ocr_hybrid와 같은 정렬 로직, OCR만 pdfplumber words로 대체 → 빠르고 정확.

parse_from_grids와 동일한 questions 리스트 반환 → build_polls 호환.
"""
from __future__ import annotations
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from poll_terms import PARTY_NAMES, HEADER_WORDS, _is_noise_name, detect_office  # noqa: E402
from parse_pdf_v2 import METRIC_TITLE_KW, is_metric_title  # noqa: E402

_PCT = re.compile(r"^\d{1,3}(?:\.\d)?$")


def _rows(page):
    """word를 행(top)으로 묶어 [(top, [(xc, text)])] 정렬 반환."""
    rows = defaultdict(list)
    for w in page.extract_words(x_tolerance=1.5, keep_blank_chars=False):
        rows[round(w["top"] / 3) * 3].append(((w["x0"] + w["x1"]) / 2, w["text"]))
    return sorted((t, sorted(v)) for t, v in rows.items())


def _title(rows) -> str:
    for _, toks in rows:
        line = "".join(t for _, t in toks)
        if re.search(r"(시장|지사|교육감|군수|구청장|단체장)", line) and \
           re.search(r"(지지|적합|선호|후보|대결|양자|투표)", line):
            return line
    return ""


def _is_total_row(toks) -> bool:
    line = "".join(t for _, t in toks)
    if not re.search(r"전\s*체|▣|■|BASE", line):
        return False
    return sum(1 for x, t in toks if _PCT.match(t) and 0 <= float(t) <= 100) >= 2


def extract_page(page) -> list[dict]:
    rows = _rows(page)
    if not rows:
        return []
    title = _title(rows)
    # 후보 title 없으면(투표의향·국정평가·현안 등) 또는 메트릭 title(선택기준·이념 등)이면 skip
    if not title or is_metric_title(title) or any(k in re.sub(r"\s", "", title) for k in METRIC_TITLE_KW):
        return []
    page_txt = " ".join(t for _, toks in rows for _, t in toks)
    out = []
    for ri, (top, toks) in enumerate(rows):
        if not _is_total_row(toks):
            continue
        pcts = [(x, float(t)) for x, t in toks if _PCT.match(t) and 0 <= float(t) <= 100]
        if len(pcts) < 2:
            continue
        # 헤더: 이 행 위 1~3행에서 이름/정당 (x별). 헤더가 2줄로 쪼개지므로 합침.
        names, parties = [], []
        for rj in range(max(0, ri - 4), ri):
            for x, t in rows[rj][1]:
                tt = re.sub(r"\s", "", t)
                pn = next((p for p in PARTY_NAMES if p in tt), "")
                if pn:
                    parties.append((x, pn))
                    tt = tt.replace(pn, "")
                m = re.fullmatch(r"[가-힣]{2,4}", tt)
                if m and tt not in HEADER_WORDS and not _is_noise_name(tt):
                    names.append((x, tt))
        # 후보지지: 이름 정렬 / 정당지지: 정당만
        is_party = bool(parties) and not names
        cands = []
        used = set()
        for px, pv in pcts:
            if is_party:
                m = min(((abs(px - bx), bp) for bx, bp in parties), default=None)
                if m and m[0] < 25 and m[1] not in used:
                    used.add(m[1]); cands.append({"name": "", "party": m[1], "pct": pv})
            else:
                m = min(((abs(px - nx), nm) for nx, nm in names), default=None)
                if m and m[0] < 30 and m[1] not in used:
                    nm = m[1]; used.add(nm)
                    party = ""
                    pm = min(((abs(px - bx), bp) for bx, bp in parties), default=None)
                    if pm and pm[0] < 35:
                        party = pm[1]
                    cands.append({"name": nm, "party": party, "pct": pv})
        if len(cands) < 2:
            continue
        office = detect_office(title, page_txt)
        if title and re.search(r"(시장|지사|교육감|군수|구청장).{0,12}(후보|지지|적합|선호|대결)",
                               re.sub(r"\s", "", title)):
            office = "후보지지"
        elif is_party:
            office = "정당지지"
        out.append({"title": title, "election_office": office or "후보지지", "candidates": cands})
        break  # 페이지당 첫 전체행
    return out


def extract_pdf(pdf_path: Path) -> dict:
    questions = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                questions += extract_page(page)
    except Exception as e:
        print(f"  words fail {pdf_path.name}: {e}", file=sys.stderr)
    ntt = pdf_path.name.split("_", 1)[0]
    return {"source_pdf": pdf_path.name, "ntt_id": ntt, "questions": questions}
