"""코리아리서치 등 '통계표' cross-tab PDF 추출 (텍스트층 정상, OCR 불필요).

레이아웃: 후보명이 헤더 열(천호성/이남호/…)에, 직책이 그 아래로 stack, 그 다음
'전 체' 행에 열별 %가 온다. parse_words는 이름 헤더가 전체행보다 ~10행 위(직책 stack)라
4행 lookback을 벗어나 실패했다. 여기선 제목~전체행 사이에서 실명행을 찾아 x로 정렬한다.

괄호 숫자((502)=사례수/가중값)는 % 아님 → 제외. 응답옵션(그외/없다/결정/모름)은 noise 필터.
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

_PCT = re.compile(r"^\d{1,3}(?:\.\d)?$")        # 괄호 없는 0~100 (사례수 (502)는 제외)
_NAME = re.compile(r"^[가-힣]{2,4}$")
_OFFICE_KW = re.compile(r"(시장|지사|교육감|군수|구청장|단체장)")
_RACE_KW = re.compile(r"(선호도|지지도|적합도|지지율|선호하|지지하|적합)")


def _rows(page):
    rows = defaultdict(list)
    for w in page.extract_words(x_tolerance=1.5, keep_blank_chars=False):
        rows[round(w["top"] / 3) * 3].append(((w["x0"] + w["x1"]) / 2, w["text"]))
    return sorted((t, sorted(v)) for t, v in rows.items())


def _flat(toks):
    return re.sub(r"\s", "", "".join(t for _, t in toks))


def extract_page(rows) -> list[dict]:
    # 제목: '표 N ... (시장|지사|교육감|군수) ... 선호도/지지도'
    title = ""
    title_ri = -1
    for ri, (top, toks) in enumerate(rows):
        line = "".join(t for _, t in toks)
        if _OFFICE_KW.search(line) and _RACE_KW.search(line) and ("표" in line or "문" in line or _flat(toks).startswith(("<표", "[표"))):
            title = line.strip()
            title_ri = ri
            break
    if not title:
        return []
    # 전체 행: 'BASE:전체' 또는 '전체'로 시작 + 괄호없는 숫자 ≥2
    total_ri = -1
    for ri in range(title_ri + 1, len(rows)):
        f = _flat(rows[ri][1])
        if re.match(r"(BASE:?전체|전체|■전체|▣전체)", f) and \
           sum(1 for x, t in rows[ri][1] if _PCT.match(t) and 0 <= float(t) <= 100) >= 2:
            total_ri = ri
            break
    if total_ri < 0:
        return []
    pcts = [(x, float(t)) for x, t in rows[total_ri][1] if _PCT.match(t) and 0 <= float(t) <= 100]
    if len(pcts) < 2:
        return []
    # 이름 헤더 행: 제목~전체행 사이에서 실명 토큰이 가장 많은 행
    best_names = []
    for ri in range(title_ri + 1, total_ri):
        names = []
        for x, t in rows[ri][1]:
            tt = re.sub(r"\s", "", t)
            if _NAME.match(tt) and tt not in HEADER_WORDS and not _is_noise_name(tt):
                names.append((x, tt))
        if len(names) > len(best_names):
            best_names = names
    if len(best_names) < 2:
        return []
    # % → 가장 가까운 이름 (x 정렬)
    cands = []
    used = set()
    for px, pv in pcts:
        m = min(((abs(px - nx), nm) for nx, nm in best_names), default=None)
        if m and m[0] < 22 and m[1] not in used:
            used.add(m[1])
            cands.append({"name": m[1], "party": "", "pct": pv})
    if len(cands) < 2:
        return []
    page_txt = title
    office = detect_office(title, page_txt)
    if _OFFICE_KW.search(title) and _RACE_KW.search(title):
        office = "후보지지"
    return [{"title": title, "election_office": office or "후보지지", "candidates": cands}]


def extract_pdf(pdf_path: Path) -> dict:
    questions = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                try:
                    questions += extract_page(_rows(page))
                except Exception:
                    pass
    except Exception as e:
        print(f"  kr-stats fail {pdf_path.name}: {e}", file=sys.stderr)
    ntt = pdf_path.name.split("_", 1)[0]
    return {"source_pdf": pdf_path.name, "ntt_id": ntt, "questions": questions}


if __name__ == "__main__":
    for f in sys.argv[1:]:
        r = extract_pdf(Path(f))
        print(f"=== {Path(f).name[:45]} → {len(r['questions'])}문항 ===")
        for q in r["questions"]:
            print(f"  [{q['election_office']}] {q['title'][:42]} | {[(c['name'], c['pct']) for c in q['candidates']]}")


def main():
    """parsed 후보 0인 결과 PDF에 이 통계표 파서를 적용해 회복분을 parsed/에 기록.
    덮어쓰기 가드: 현 parsed에 후보(pct)가 이미 있으면 건드리지 않는다 (다른 파서 결과 보존)."""
    import glob
    import json
    root = Path(__file__).resolve().parent.parent
    nok = nq = 0
    for pf in glob.glob(str(root / "data/raw/pdf/*.pdf")):
        b = Path(pf).name
        if any(k in b for k in ("설문", "질문", "보도")):
            continue
        out = root / "data/raw/parsed" / (Path(pf).stem + ".json")
        if out.exists():
            cur = json.loads(out.read_text(encoding="utf-8"))
            if any(q.get("candidates") and any("pct" in c for c in q["candidates"])
                   for q in cur.get("questions", [])):
                continue  # 이미 후보 있음 → skip
        r = extract_pdf(Path(pf))
        if any(q["candidates"] for q in r["questions"]):
            out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
            nok += 1
            nq += sum(1 for q in r["questions"] if q["candidates"])
    print(f"kr-stats 회복: {nok} PDF, {nq} 문항", file=sys.stderr)


if __name__ == "__main__" and len(sys.argv) == 1:
    main()
