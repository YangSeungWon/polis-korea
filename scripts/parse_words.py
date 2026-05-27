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
from poll_terms import PARTY_NAMES, HEADER_WORDS, _is_noise_name, detect_office, PARTY_CANON  # noqa: E402
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
                    parties.append((x, PARTY_CANON.get(pn, pn)))
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


def _result_pdf(ntt: str):
    import glob
    for pat in (f"data/raw/pdf/{ntt}_*결과*.pdf", f"data/raw/pdf/{ntt}_*통계*.pdf",
                f"data/raw/pdf/{ntt}_*집계*.pdf"):
        g = glob.glob(pat)
        if g:
            return g[0]
    g = [f for f in glob.glob(f"data/raw/pdf/{ntt}_*.pdf")
         if not any(k in f for k in ("설문", "질문", "보도"))]
    return g[0] if g else None


def _ntitle(t: str) -> str:
    return re.sub(r"[\s\[\]【】<>()표\d.·_-]+", "", t or "")


_PREFIX_LEAK = re.compile(r"^기[가-힣]{2,3}$")  # "기이장우" = 기호 number가 이름에 붙은 격자 artifact
_BAD_WORDNAME = {"사람", "사람이", "다음", "인물", "후보"}


def _clean_names(cands) -> bool:
    """word 후보가 모두 깨끗한 이름인지 (FP 방지 가드 — 사람/사람이/truncation 거부)."""
    ns = [c["name"] for c in cands if c.get("name")]
    return bool(ns) and all(
        re.fullmatch(r"[가-힣]{2,4}", n) and n not in _BAD_WORDNAME and not _is_noise_name(n)
        for n in ns)


def fix_prefix_leak() -> tuple[int, int]:
    """격자가 '기OOO'(기호 leak)로 이름을 망친 후보지지를, word 추출이 깨끗하면 교체.

    blanket word-merge는 충북 도지사 등을 '사람/사람이'로 망치는 FP가 있어(전수검증 확인) 폐기.
    대신 '기'-leak는 격자의 알려진 실패 모드라, 그 표만 word로 — word 결과가 깨끗할 때만.
    """
    import glob
    import json
    root = Path(__file__).resolve().parent.parent
    n_pdf = n_repl = 0
    for pf in glob.glob(str(root / "data/raw/parsed/*.json")):
        try:
            d = json.loads(Path(pf).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not any(q.get("election_office") in CAND_OFFICE and
                   any(_PREFIX_LEAK.match(c.get("name", "")) for c in q.get("candidates", []))
                   for q in d.get("questions", [])):
            continue
        pdfs = glob.glob(str(root / "data/raw/pdf" / (Path(pf).stem + ".pdf")))
        if not pdfs:
            continue
        wq = {_ntitle(q["title"]): q for q in extract_pdf(Path(pdfs[0]))["questions"]
              if len(q["candidates"]) >= 2}
        changed = False
        for q in d["questions"]:
            w = wq.get(_ntitle(q.get("title", "")))
            if (w and q.get("election_office") in CAND_OFFICE
                    and len(w["candidates"]) >= len(q.get("candidates", []))
                    and _clean_names(w["candidates"])):
                q["candidates"] = w["candidates"]
                changed = True
                n_repl += 1
        if changed:
            Path(pf).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            n_pdf += 1
    return n_pdf, n_repl


CAND_OFFICE = ("후보지지", "적합도", "당선가능성")


def main():
    """image_no_table(표 선 없는 텍스트 PDF) 추출 + 격자 '기'-leak word 교체 → parsed/."""
    import json
    import subprocess
    import time
    root = Path(__file__).resolve().parent.parent
    img = [l.split(" | ")[0] for l in subprocess.run(
        [sys.executable, "scripts/audit_parse.py", "--list", "image_no_table"],
        capture_output=True, text=True).stdout.splitlines()]
    t = time.time()
    nok = nq = 0
    for ntt in img:
        f = _result_pdf(ntt)
        if not f:
            continue
        r = extract_pdf(Path(f))
        cand_q = [q for q in r["questions"] if q["candidates"]]
        if cand_q:
            out = root / "data/raw/parsed" / (Path(f).stem + ".json")
            out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
            nok += 1
            nq += len(cand_q)
    np, nr = fix_prefix_leak()
    print(f"words 파싱: {nok} PDF 회복 {nq} 문항 · 기-leak 교체 {nr}({np} PDF) / {time.time()-t:.0f}s",
          file=sys.stderr)


if __name__ == "__main__":
    main()
