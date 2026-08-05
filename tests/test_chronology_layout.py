"""연표 레이아웃 — 넓은 화면에서 벌어지고, 좁은 화면에서 좁아지는지.

2026-08-05: 페이지가 1320px인데 연표 행이 그 폭을 다 써서, 우측 정렬된 결과 막대가
사건 텍스트에서 500px 넘게 떨어져 있었다. 같은 행인데 눈으로 안 붙고 화면 중앙이
통째로 비어 'CSS 깨진 페이지'처럼 읽혔다.

폭을 묶어 고쳤는데, 이런 수정은 반대쪽(모바일)을 깨기 쉽다. 브라우저가 없으므로
CSS 규칙 자체를 검사한다 — 렌더링이 아니라 '제한이 좁은 화면에서 풀리는가'다.

실행: .venv/bin/python tests/test_chronology_layout.py
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_RAW = (ROOT / "assets/chronology.css").read_text(encoding="utf-8")
# 주석은 셀렉터 앞에 붙어 파싱을 어긋나게 한다 — 먼저 걷어낸다.
CSS = re.sub(r"/\*[\s\S]*?\*/", "", _RAW)
MOBILE_BP = 560

fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def rules(css: str) -> list[tuple[str, str]]:
    """(셀렉터, 선언부) 목록. 셀렉터는 마지막 줄만 — 앞 줄은 @media 등 상위 문맥이다."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel = m.group(1).strip().split("\n")[-1].strip()
        if sel and not sel.startswith("@"):
            out.append((sel, m.group(2)))
    return out


def main():
    # 미디어쿼리 안/밖 분리 — 안쪽이 좁은 화면 규칙이다.
    mq = re.search(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{([\s\S]*?)\n\}", CSS)
    ck("모바일 미디어쿼리가 있다", bool(mq))
    if not mq:
        print("\n실패 1")
        return 1
    bp, inner = int(mq.group(1)), mq.group(2)
    ck(f"모바일 분기점이 {MOBILE_BP}px 이하", bp <= MOBILE_BP, str(bp))

    outer = CSS[:mq.start()] + CSS[mq.end():]

    def merged(rs, sel):
        """같은 셀렉터가 여러 번 나오면 선언을 합쳐서 본다 — 실제 캐스케이드와 같게."""
        return " ".join(b for s2, b in rs if s2 == sel)

    orules = rules(outer)

    # ── 1. 넓은 화면: 폭이 묶여 있다 ────────────────────────────────────────
    chrono = merged(orules, ".chrono")
    m = re.search(r"max-width:\s*(\d+)px", chrono)
    ck("연표에 max-width가 있다", bool(m), chrono[:60])
    if m:
        w = int(m.group(1))
        # 너무 좁으면 사건 제목이 줄바꿈 지옥, 너무 넓으면 원래 문제가 남는다.
        ck(f"연표 폭이 합리적 범위 (600~960px, 지금 {w})", 600 <= w <= 960, str(w))
    ck("연표가 가운데 정렬", "margin: 0 auto" in chrono or "margin:0 auto" in chrono)

    body = merged(orules, ".chr-body")
    ck("본문 폭이 묶여 있다 (결과 막대가 멀어지지 않게)",
       "max-width" in body, body[:60])

    # ── 2. 좁은 화면: 제한이 풀린다 ─────────────────────────────────────────
    irules = rules(inner)
    ck("모바일에서 본문 폭 제한 해제",
       "max-width: none" in merged(irules, ".chr-body"), merged(irules, ".chr-body") or "(없음)")
    ck("모바일에서 레일이 좁아진다", "--rail" in merged(irules, ".chrono"),
       merged(irules, ".chrono") or "(없음)")

    # ── 3. 좁은 화면을 넘치는 고정 폭이 없다 ────────────────────────────────
    # max-width는 상한이라 안전하지만, width 고정은 320px 화면을 넘치게 만든다.
    wide = []
    for sel, b in rules(CSS):
        for mm in re.finditer(r"(?<!max-)(?<!min-)width:\s*(\d+)px", b):
            if int(mm.group(1)) > 320:
                wide.append(f"{sel.strip()}={mm.group(1)}px")
    ck("320px를 넘는 고정 width 없음", not wide, str(wide[:4]))

    # ── 4. 제목·필터가 연표와 같은 폭 ───────────────────────────────────────
    ctrl = merged(orules, ".chrono-controls")
    ck("필터도 같은 폭으로 정렬", "max-width" in ctrl, ctrl[:60])

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
