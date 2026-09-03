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
    # ⚠️ 쌍을 **손으로 적지 않는다.** 2026-08 사고 직후 3쌍만 적어 뒀는데, 나중에
    # 생긴 /history/local/{n}/governor·superintendent가 그 목록에 없었다. 그래서
    # governor의 유일한 표 16행이 archive의 「시도별 광역단체장」과 **100% 같은
    # 행**인 채로 1년 가까이 지나갔다(2026-09-03 발견). 목록을 손으로 관리하면
    # 새로 생긴 쪽은 늘 빠진다 — 디스크에서 열거한다.
    def hist_of(slug):
        import json as _j
        try:
            m = _j.loads((ROOT / f"data/elections/{slug}.json").read_text(encoding="utf-8"))
        except Exception:
            return []
        kind, n = m.get("kind"), m.get("n")
        if kind == "local":
            base = ROOT / f"history/local/{n}"
            return [f"history/local/{n}/{d.name}" for d in sorted(base.glob("*"))
                    if (d / "index.html").is_file()]
        seg = {"presidential": "presidential",
               "national_assembly": "national-assembly"}.get(kind)
        p2 = f"history/{seg}/{n}" if seg else None
        return [p2] if p2 and (ROOT / p2 / "index.html").is_file() else []

    pairs = []
    for d in sorted((ROOT / "archive").glob("*")):
        if not (d / "index.html").is_file():
            continue
        pairs += [(f"archive/{d.name}", h) for h in hist_of(d.name)]
    # **표 대 표 최대 유사도로 재지 않는다.** 그러면 '요약 + 상세' 패턴이 늘
    # 빨개진다 — 상세 페이지가 위에 16행 요약을 두고 아래에 256행 상세를 두는 건
    # 정상이고, 그 요약이 archive의 표와 같은 건 당연하다. 문제는 "같은 화면이 두
    # URL에 있는가"이므로 **페이지 단위**로 잰다: B의 표 행 중 몇 %가 A에도 있나.
    #   고침 전 governor 16/16 = 100%  ← 페이지 전체가 복사본이었다
    #   고침 후 governor 16/272 = 6%   ← 요약만 겹치고 본문은 자기 것이다
    #   mayor 0%                       ← 원래 정상
    def rowset(f):
        h = re.sub(r"<script.*?</script>", "", f.read_text(encoding="utf-8"), flags=re.S)
        out = set()
        for tb in re.finditer(r'<table class="pp-static".*?</table>', h, re.S):
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tb.group(0), re.S):
                cells = tuple(re.sub(r"<[^>]+>", "", c).strip()
                              for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S))
                if cells:
                    out.add(cells)
        return out

    worst = []
    for a, h in pairs:
        fa, fh = ROOT / a / "index.html", ROOT / h / "index.html"
        if not (fa.is_file() and fh.is_file()):
            continue
        ra, rh = rowset(fa), rowset(fh)
        if not rh:
            continue
        worst.append((len(ra & rh) / len(rh), a, h))
    worst.sort(reverse=True)
    for r, a, h in worst[:3]:
        print(f"    {r:.0%}  {h}의 표 행 중 {a}에도 있는 것")

    # 겹쳐도 되는 경우가 하나 있다 — 실을 내용이 아예 없어서 **그렇다고 선언한** 쪽.
    # /history/local/{1..4}/governor는 NEC가 그 회차 광역단체장의 시군구별 득표를
    # 주지 않아 16행 요약이 전부다. 그런 쪽은 canonical이 archive를 가리키고
    # sitemap에서도 빠진다. 그러니 기준은 "겹치지 않는다"가 아니라 **"겹치면
    # 선언돼 있다"**이다 — 조용한 중복만 막는다.
    def canon_of(path):
        h = (ROOT / path / "index.html").read_text(encoding="utf-8")
        m = re.search(r'<link rel="canonical" href="([^"]*)"', h)
        return (m.group(1) if m else "").replace("https://polis.ysw.kr", "")

    undeclared = [f"{h} {r:.0%}" for r, a, h in worst
                  if r >= 0.6 and canon_of(h) == f"/{h}/"]
    ck(f"archive↔history 쌍 {len(pairs)}개에 **선언 안 된** 중복이 없다",
       not undeclared, str(undeclared[:3]))

    # 선언한 쪽은 sitemap에도 없어야 한다. 페이지는 "저기가 정본"이라 하는데
    # sitemap이 "여기를 색인해 달라"고 하면 두 신호가 어긋난다.
    sm = (ROOT / "sitemap-history.xml")
    if sm.is_file():
        raw2 = sm.read_text(encoding="utf-8")
        leaked = [h for r, a, h in worst if r >= 0.6 and canon_of(h) != f"/{h}/"
                  and f"/{h}/" in raw2]
        ck("canonical을 넘긴 쪽이 sitemap에 없다", not leaked, str(leaked[:3]))

    # 한 페이지 안에서도 마찬가지다. 22대 archive는 「시도별 지역구 의석」과
    # 「지역구 — 시도별」을 함께 걸고 있었는데 앞의 것이 뒤의 것의 부분집합이었다.
    # 페이지 밖만 보는 검사는 그걸 못 본다.
    inner = []
    for d in sorted((ROOT / "archive").glob("*")):
        f = d / "index.html"
        if not f.is_file():
            continue
        ts = tables(f)
        for i in range(len(ts)):
            for j2 in range(i + 1, len(ts)):
                r = difflib.SequenceMatcher(None, ts[i], ts[j2]).ratio()
                if r >= 0.75:
                    inner.append(f"{d.name} 표{i}↔표{j2} {r:.0%}")
    ck(f"archive 한 쪽 안에 겹치는 표가 없다 ({len(pairs)}쪽 검사)", not inner, str(inner[:3]))


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
