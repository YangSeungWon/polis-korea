"""정적 본문 하한 — 렌더 없이 읽히는 내용이 있는가.

2026-08 GSC 전수 측정에서 archive·history가 거의 전부 미색인이었다. 원인을 찾다
보니 페이지가 **비어 있었다**:

    archive/21st-pres-2025/        정적 텍스트 1,120자 · hidden 섹션 6개
    history/national-assembly/19/  정적 텍스트   648자 · 본문이 "데이터 불러오는 중…"
    region/강원특별자치도-강릉시/    정적 텍스트 1,953자 · 지도가 없는데 가장 두껍다

결과 섹션이 전부 빈 껍데기고 JS가 채운다. region만 표를 정적으로 내고 있었고,
그게 이 저장소가 이미 갖고 있던 정답이라 archive를 그렇게 만들었다.

**이 검사가 있었다면 그 상태를 잡았다.** 다른 검사들은 전부 초록이었다 — 구조도
링크도 sitemap도 멀쩡했고, 없는 건 '내용'이었는데 아무도 그걸 안 재고 있었다.

하한은 '지금보다 나빠지지 않는다' 수준으로 잡는다. 목표치가 아니라 회귀 방지선이다.
계열마다 원래 두께가 다르므로(간선 대선은 시도별 데이터가 존재하지 않는다) 중앙값을
본다 — 최소값을 보면 '없는 게 맞는' 회차 때문에 영구히 빨갛다.

실행: .venv/bin/python tests/test_static_content.py
"""
from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (이름, glob, 중앙값 하한). 실측 중앙값의 8할 남짓 — 회귀는 잡되 회차 구성이 조금
# 바뀌는 것으로는 안 울린다.
#
# ⚠️ archive가 history보다 낮은 게 정상이다. 두 계열은 **입도가 다르다**:
#     archive/{선거}            시도 집계 (17행) — 그 선거 전체를 요약
#     history/{종류}/{n}/{직위}   시군구·선거구 상세 (227~254행)
# 한때 archive에도 상세를 냈다가 본문이 100% 같아졌다. 같은 질의를 두고 우리
# 페이지끼리 경쟁하는 상태다 — 그래서 archive는 얇은 게 아니라 접혀 있는 것이다.
# archive 하한을 5,000으로 올리려면 history에서 뭘 가져올지부터 정해야 한다.
FAMILIES = [
    ("archive", "archive/*/index.html", 1400),
    ("history", "history/*/*/**/index.html", 5000),
    ("region",  "region/*/index.html",  1500),
]

fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def static_text(html: str) -> str:
    """크롤러가 렌더 없이 보는 텍스트. <script>·<style>은 뺀다."""
    t = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()


def check_no_duplicate_tables() -> None:
    """archive와 history가 **같은 표**를 갖고 있지 않은가.

    2026-08 실제로 만들었던 사고다. 둘 다 비어 있던 동안에는 잠복해 있던 문제가
    (docs/page-map.md gap-3 "같은 화면의 두 URL") 본문을 채우자마자 드러났다 —
    archive/9th-local-2026의 기초단체장 227행과 history/local/9/mayor의 227행이
    글자 단위로 동일했다.

    입도로 나눈다: archive는 시도 집계, history는 시군구·선거구 상세.
    표 본문이 크게 겹치면 그 구분이 무너진 것이다.
    """
    import difflib

    def tables(f: Path) -> list[str]:
        """표를 **한 장씩** 돌려준다. 이어붙여 비교하면 희석된다 — archive에 표가
        여러 개라, 227행짜리 하나를 통째로 베껴 와도 합산 유사도는 13%로 나온다
        (2026-08 변이 시험에서 실제로 안 잡혔다). 표 대 표로 봐야 한다."""
        h = f.read_text(encoding="utf-8")
        return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(0)))
                for m in re.finditer(r'<table class="pp-static".*?</table>', h, re.S)]

    print("\n[중복] archive와 history가 같은 표를 갖지 않는가")
    pairs = [("archive/9th-local-2026", "history/local/9/mayor"),
             ("archive/21st-pres-2025", "history/presidential/21"),
             ("archive/22nd-general-2024", "history/national-assembly/22")]
    worst = []
    for a, h in pairs:
        fa, fh = ROOT / a / "index.html", ROOT / h / "index.html"
        if not (fa.is_file() and fh.is_file()):
            continue
        ta, th = tables(fa), tables(fh)
        # 어느 한 쌍이라도 크게 겹치면 그 구분이 무너진 것이다.
        r = max((difflib.SequenceMatcher(None, x, y).ratio() for x in ta for y in th),
                default=0.0)
        worst.append((r, a, h))
    for r, a, h in worst:
        ck(f"{a.split('/')[1]} ↔ {h} 겹침 {r:.0%} < 50%", r < 0.5,
           "같은 표를 두 URL이 갖고 있다 — 입도(시도 vs 시군구)가 무너졌다")


def main() -> int:
    print("[본문] 렌더 없이 읽히는 텍스트")
    for label, pat, floor in FAMILIES:
        lens = [len(static_text(f.read_text(encoding="utf-8")))
                for f in sorted(ROOT.glob(pat))]
        if not lens:
            ck(f"{label} 페이지가 있다", False, pat)
            continue
        med = statistics.median(lens)
        ck(f"{label} {len(lens)}쪽 중앙값 {med:,.0f}자 ≥ {floor:,}", med >= floor,
           f"본문이 얇아졌다 — 생성기가 정적 표를 안 내고 있는지 볼 것")

    # archive 결과 섹션이 다시 hidden으로 돌아가지 않았는가.
    # 정적 표를 넣어도 섹션이 hidden이면 제목까지 안 읽힌다.
    print("\n[섹션] 정적 표가 숨겨져 있지 않은가")
    hidden = []
    for f in sorted(ROOT.glob("archive/*/index.html")):
        h = f.read_text(encoding="utf-8")
        for sec in ("ar-region-table", "ar-detail-table"):
            if re.search(rf'<section[^>]*id="{sec}"[^>]*\shidden', h):
                hidden.append(f"{f.parent.name}/{sec}")
    ck("정적 표 섹션이 hidden이 아니다", not hidden, str(hidden[:3]))

    check_no_duplicate_tables()

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
