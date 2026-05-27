"""CID 폰트 PDF 하이브리드 추출 — 숫자는 pdfplumber 좌표, 이름은 OCR.

여론조사꽃 등은 텍스트층 한글이 (cid:..)로 깨졌지만:
  - 퍼센트 숫자(ASCII)는 pdfplumber가 좌표·소수점까지 정확히 디코드 (단 칼럼 병합).
  - 렌더 이미지는 선명한 한글 → OCR로 후보명·"전체" 라벨·제목을 읽음.
전략: OCR로 구조(제목·전체행 위치·후보명+x)를 잡고, pdfplumber extract_words로
그 행의 퍼센트를 x별로 가져와 정렬. 숫자는 OCR 안 거치므로 신뢰 가능.

parse_from_grids와 같은 questions 리스트를 반환 → build_polls 호환.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from poll_terms import PARTY_NAMES, _is_noise_name, detect_office  # noqa: E402

# 후보가 행으로 들어간 transposed 표 감지용 ("민주당 김상욱" 시작 행). 이 hybrid는
# 후보=열 가정이라 transposed면 전체값 컬럼을 신뢰성 있게 못 짚음 → skip(틀린값 방지).
_ROW_CAND = re.compile(
    r"^(?:더불어민주당|국민의힘|조국혁신당|개혁신당|진보당|정의당|기본소득당|새로운미래|사회민주당|무소속)"
    r"\s*[가-힣]{2,4}")

DPI = 150
SCALE = DPI / 72.0  # pdf point → 렌더 픽셀

_OCR = None


def _ocr():
    global _OCR
    if _OCR is None:
        from paddleocr import PaddleOCR
        _OCR = PaddleOCR(use_angle_cls=False, lang="korean", show_log=False)
    return _OCR


def _ocr_boxes(pdf_path: Path, page_index: int):
    """[(xc_img, yc_img, text)] — 이미지 좌표."""
    doc = fitz.open(pdf_path)
    pix = doc[page_index].get_pixmap(dpi=DPI)
    import numpy as np
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    img = img[:, :, :3] if pix.n >= 3 else img
    res = _ocr().ocr(img[:, :, ::-1].copy(), cls=False)
    out = []
    for line in (res[0] or []) if res else []:
        box, (txt, conf) = line
        if conf < 0.5 or not txt.strip():
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append((sum(xs) / 4, sum(ys) / 4, txt.strip()))
    return out


_PCT = re.compile(r"^\d{1,3}\.\d$")


def _pdf_word_rows(page):
    """pdfplumber 단어를 행(top)으로 묶어 [(top, [(x_center, text)])]."""
    words = page.extract_words(x_tolerance=1.5, keep_blank_chars=False)
    from collections import defaultdict
    rows = defaultdict(list)
    for w in words:
        rows[round(w["top"] / 3) * 3].append(((w["x0"] + w["x1"]) / 2, w["text"]))
    return sorted((t, sorted(v)) for t, v in rows.items())


def _pcts_at(pdf_rows, pdf_top, tol=8):
    """주어진 pdf-top 근처 행의 퍼센트 토큰 [(x_center, value)]."""
    best = None
    for top, toks in pdf_rows:
        if abs(top - pdf_top) <= tol:
            best = toks
            break
    if best is None:
        return []
    return [(x, float(t)) for x, t in best if _PCT.match(t) and 0 <= float(t) <= 100]


def extract_page(pdf_path: Path, page_index: int) -> list[dict]:
    """한 페이지에서 후보지지/정당지지 questions 추출."""
    ocr = _ocr_boxes(pdf_path, page_index)
    if not ocr:
        return []
    with pdfplumber.open(pdf_path) as pdf:
        pdf_rows = _pdf_word_rows(pdf.pages[page_index])

    # OCR 행 묶기 (이미지 y)
    from collections import defaultdict
    orows = defaultdict(list)
    for x, y, t in ocr:
        orows[round(y / 12) * 12].append((x, t))
    orows = sorted((y, sorted(v)) for y, v in orows.items())

    # 제목 — 시장/지사/교육감 + 지지/후보/대결 들어간 OCR 텍스트.
    # 후보 title이 없으면(정당지지·국정평가·현안 페이지) 추출 안 함 → 오추출 방지.
    page_txt = " ".join(t for _, _, t in ocr)
    title = ""
    for y, toks in orows:
        line = "".join(t for _, t in toks)
        if re.search(r"(시장|지사|교육감|군수|구청장|단체장)", line) and \
           re.search(r"(지지|적합|선호|후보|대결|양자|투표)", line):
            title = line
            break
    if not title:
        return []

    # transposed(후보=행) 감지 — "정당+이름"으로 시작하는 행이 ≥2개면 후보=열 가정이 깨짐.
    # 이 hybrid는 transposed의 전체값 컬럼을 신뢰성 있게 못 짚으므로 skip(틀린 김상/없디 방지).
    if sum(1 for _, toks in orows
           if toks and _ROW_CAND.match("".join(t for _, t in toks[:3]))) >= 2:
        return []

    questions = []
    # "전체" OCR 박스 → 그 행의 퍼센트(pdfplumber) + 위쪽 후보명(OCR)
    for y, toks in orows:
        if not any(re.search(r"전\s*체|^전체$|▣?전체▣?", t) for _, t in toks):
            continue
        pdf_top = y / SCALE
        pcts = _pcts_at(pdf_rows, pdf_top)
        if len(pcts) < 2:
            continue
        # 후보명: 전체 행 위쪽 1~2 OCR 행에서 후보명/정당명 (x별)
        names = []   # (x_img, name)
        parties = []  # (x_img, party)
        for yy, hh in orows:
            if not (y - 60 <= yy < y):
                continue
            for x, t in hh:
                tt = re.sub(r"\s", "", t)
                p = next((pn for pn in PARTY_NAMES if pn in tt), "")
                if p:
                    parties.append((x, p))
                    tt = tt.replace(p, "")
                m = re.fullmatch(r"[가-힣]{2,4}", tt)
                if m and not _is_noise_name(tt):
                    names.append((x, tt))
        if not names:
            continue
        # 정렬: 각 퍼센트(pdf x → img x)에 가장 가까운 이름
        cands = []
        used = set()
        for px, pv in pcts:
            ix = px * SCALE
            cand = min(((abs(ix - nx), nx, nm) for nx, nm in names), default=None)
            if cand and cand[0] < 40 and cand[2] not in used:
                nm = cand[2]
                used.add(nm)
                party = ""
                pm = min(((abs(ix - bx), bp) for bx, bp in parties), default=None)
                if pm and pm[0] < 50:
                    party = pm[1]
                cands.append({"name": nm, "party": party, "pct": pv})
        if len(cands) >= 2:
            # title이 후보 race임을 이미 확인했으므로 후보지지 (detect_office는 "대결"을 못 잡음)
            questions.append({"title": title, "election_office": "후보지지",
                              "candidates": cands})
        break  # 페이지당 첫 전체행(주 결과)만
    return questions


def candidate_pages(pdf_path: Path) -> list[int]:
    """OCR 전 사전스캔(빠름): 퍼센트 행(≥3개 0~100 소수)이 있는 page만. 표지·방법론 제외."""
    out = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for pi, page in enumerate(pdf.pages):
                for _, toks in _pdf_word_rows(page):
                    if sum(1 for _, t in toks if _PCT.match(t) and 0 <= float(t) <= 100) >= 3:
                        out.append(pi)
                        break
    except Exception as e:
        print(f"  prescan fail {pdf_path.name}: {e}", file=sys.stderr)
    return out


def extract_pdf(pdf_path: Path, page_indices: list[int] | None = None) -> dict:
    if page_indices is None:
        page_indices = candidate_pages(pdf_path)
    questions = []
    for pi in page_indices:
        try:
            questions += extract_page(pdf_path, pi)
        except Exception as e:
            print(f"  ocr-hybrid fail {pdf_path.name} p{pi}: {e}", file=sys.stderr)
    ntt = pdf_path.name.split("_", 1)[0]
    return {"source_pdf": pdf_path.name, "ntt_id": ntt, "questions": questions}
