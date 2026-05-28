"""cid 깨진 PDF 한글 복구 helper.

여론조사꽃·일부 PDF는 NotoSansKR subset + ToUnicode CMap에 한글 매핑 누락.
pymupdf로 text 뽑으면 한글이 다른 글자(예: "조사"→"혗햠")로 보임 — Identity-H라
cid 값이 그대로 unicode로 출력되기 때문.

원리: PDF의 cid는 Adobe-Korea1 supplement(NotoSansCJK)의 CID와 동일. NotoSansCJK-Regular의
KR variant cmap에 `unicode → "cid<N>"` glyph name 매핑이 있어 역(`cid → unicode`)을 추출 가능.

사용:
    from cid_decode import repair_text, build_cid_table
    fixed = repair_text(broken)              # 자동으로 default 매핑 load
    # 또는 명시:
    table = build_cid_table()                # cid → unicode dict
    fixed = repair_text(broken, table)

또는 CLI:
    python scripts/cid_decode.py path/to/cid_broken.pdf            # 전 page 복구 출력
    python scripts/cid_decode.py path/to/file.pdf --page 7         # 특정 page만
"""
from __future__ import annotations
import argparse
import sys
from functools import lru_cache
from pathlib import Path

NOTOCJK_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
# NotoSansCJK 컬렉션 내 Korean variant index (font[1])
KR_FONT_INDEX = 1


@lru_cache(maxsize=1)
def build_cid_table(path: str = NOTOCJK_PATH, font_index: int = KR_FONT_INDEX) -> dict[int, int]:
    """CID → Unicode codepoint 매핑."""
    from fontTools.ttLib import TTCollection
    tt = TTCollection(path)
    font = tt.fonts[font_index]
    cmap = font.getBestCmap()
    out = {}
    for uc, gname in cmap.items():
        if gname.startswith("cid"):
            try:
                out[int(gname[3:])] = uc
            except ValueError:
                continue
    return out


def repair_text(text: str, cid_table: dict[int, int] | None = None) -> str:
    """깨진 PDF 한글 복구.

    - ASCII (cp ≤ 0x7E): 그대로 (실제 ASCII 문자, cid 매핑 적용 시 깨짐)
    - cid_table에 있고 결과가 한글 음절(U+AC00~U+D7AF): 적용
    - 그 외: 원본 char 유지
    """
    if cid_table is None:
        cid_table = build_cid_table()
    out = []
    for ch in text:
        cp = ord(ch)
        if cp <= 0x7E:
            out.append(ch)
            continue
        uc = cid_table.get(cp)
        if uc is not None and 0xAC00 <= uc <= 0xD7AF:
            out.append(chr(uc))
        else:
            out.append(ch)
    return "".join(out)


_COMMON_WORDS = ["조사", "결과", "전체", "사례", "응답", "지지", "정당", "후보", "선거", "도", "시", "군", "구"]


def needs_repair(text: str) -> bool:
    """text가 cid 깨짐 의심.

    cid가 정상 한글 unicode와 겹쳐서 단순 코드포인트 검사로는 구분 안 됨.
    NESDC PDF에 자주 등장하는 키워드("조사·결과·전체·후보" 등)가 하나도 없는데
    한글이 다수 있으면 cid 깨짐으로 판단.
    """
    if not text:
        return False
    has_hangul = any(0xAC00 <= ord(c) <= 0xD7AF for c in text)
    if not has_hangul:
        return False
    return not any(w in text for w in _COMMON_WORDS)


def repair_pdf_page(pdf_path: str | Path, page_index: int) -> str:
    import fitz
    doc = fitz.open(str(pdf_path))
    return repair_text(doc[page_index].get_text("text"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, default=None, help="특정 페이지만")
    args = ap.parse_args()
    import fitz
    doc = fitz.open(args.pdf)
    pages = [args.page] if args.page is not None else range(len(doc))
    for pi in pages:
        raw = doc[pi].get_text("text")
        if not raw.strip():
            continue
        print(f"=== page {pi} ===")
        print(repair_text(raw))
        print()


if __name__ == "__main__":
    main()
