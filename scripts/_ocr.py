"""PaddleOCR 기반 PDF 텍스트 추출.

여론조사꽃처럼 ToUnicode CMap 제거된 PDF용. pdfplumber·PyMuPDF가 깨진 글리프
반환할 때 fallback. paddle 2.6 + OneDNN, 페이지 평균 13초/CPU.

함수:
- is_broken_text(s): 깨진 글리프 비율 검사 (PUA U+E000-U+F8FF)
- ocr_pdf_page_words(page, dpi=200): fitz.Page → words list ({text, x0, x1, top, bottom})
- ocr_pdf_to_pages(pdf_path): paged list of (words, full_text)
"""
from __future__ import annotations
import os
import tempfile
from pathlib import Path

# OneDNN 가속 활성화 (paddle 2.6 호환)
os.environ.setdefault('FLAGS_use_mkldnn', '1')


_OCR = None


def get_ocr():
    """싱글톤 PaddleOCR 인스턴스. 첫 호출에 모델 로드 (1-2초)."""
    global _OCR
    if _OCR is None:
        from paddleocr import PaddleOCR
        _OCR = PaddleOCR(
            lang='korean',
            use_angle_cls=False,
            enable_mkldnn=True,
            show_log=False,
        )
    return _OCR


# 한국어 텍스트에서 매우 흔한 글자 (조사·어미). 정상 한국어 PDF면 5%+ 등장.
# 깨진 폰트는 한글 코드 영역(U+AC00~D7A3) 안 쪽에 매핑되어도 이 글자들이 거의 없음.
_COMMON_HANGUL = set("이가는의을를도와에서다하나로한것수있고만지나")


def is_broken_text(text: str, threshold: float = 0.05) -> bool:
    """텍스트가 깨진 글리프 위주인지.

    검출 신호 (어느 하나 만족하면 broken):
    - `(cid:NNNNN)` literal 텍스트 (pdfplumber fallback)
    - PUA (U+E000-U+F8FF) 비율 > threshold
    - 한글 비율 < 5% (한국어 PDF인데 한글 거의 없음)
    - 한글이 충분한데 (>10%) 흔한 글자 비율 < 0.5% (한글 영역 폰트 mapping이 깨짐)
    """
    if not text or len(text) < 50:
        return False
    n = len(text)
    pua = sum(1 for c in text if 0xE000 <= ord(c) <= 0xF8FF)
    cid_count = text.count('(cid:')
    hangul = sum(1 for c in text if 0xAC00 <= ord(c) <= 0xD7A3)
    common = sum(1 for c in text if c in _COMMON_HANGUL)

    if cid_count >= 5:
        return True
    if pua / n > threshold:
        return True
    # 한글 비율 5% 미만 → 한국어 PDF가 아니거나 깨짐
    if hangul / n < 0.05 and n > 200:
        return True
    # 한글은 많은데 흔한 글자가 거의 없음 → 폰트 mapping 깨짐 (여론조사꽃 패턴)
    if hangul / n > 0.10 and common / n < 0.005:
        return True
    return False


def ocr_image_to_words(img_path: str, dpi: int = 200) -> list[dict]:
    """이미지 OCR → pdfplumber 형식 words list.

    pdfplumber 좌표는 PDF point (72 dpi). OCR pixel을 변환.
    """
    ocr = get_ocr()
    result = ocr.ocr(img_path, cls=False)
    if not result or not result[0]:
        return []
    scale = 72.0 / dpi
    words = []
    for line in result[0]:
        bbox, (text, conf) = line
        if conf < 0.5 or not text:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        # OCR 한 box 안에 여러 단어/공백 있을 수 있음 — split해서 같은 box 분배
        tokens = text.split()
        if not tokens:
            continue
        if len(tokens) == 1:
            words.append({
                'text': tokens[0],
                'x0': min(xs) * scale,
                'x1': max(xs) * scale,
                'top': min(ys) * scale,
                'bottom': max(ys) * scale,
            })
        else:
            # 토큰 길이 비례로 box 가로 분할
            total_chars = sum(len(t) for t in tokens) or 1
            x_start = min(xs) * scale
            x_end = max(xs) * scale
            top = min(ys) * scale
            bottom = max(ys) * scale
            cursor = x_start
            box_w = x_end - x_start
            for tok in tokens:
                tw = box_w * (len(tok) / total_chars)
                words.append({
                    'text': tok,
                    'x0': cursor,
                    'x1': cursor + tw,
                    'top': top,
                    'bottom': bottom,
                })
                cursor += tw
    return words


def ocr_pdf_page(page, dpi: int = 200) -> tuple[list[dict], str]:
    """fitz.Page → (words, full_text)."""
    pix = page.get_pixmap(dpi=dpi)
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        tmp_path = f.name
    try:
        pix.save(tmp_path)
        words = ocr_image_to_words(tmp_path, dpi=dpi)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    # full_text: words를 top·x0 순서로 정렬해서 join
    sorted_w = sorted(words, key=lambda w: (round(w['top'] / 6), w['x0']))
    full_text = ' '.join(w['text'] for w in sorted_w)
    return words, full_text


def ocr_pdf_to_pages(pdf_path: str | Path, dpi: int = 200) -> list[tuple[list[dict], str]]:
    """PDF → page별 (words, full_text) 리스트."""
    import fitz
    doc = fitz.open(str(pdf_path))
    return [ocr_pdf_page(p, dpi=dpi) for p in doc]
