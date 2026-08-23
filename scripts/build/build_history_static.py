"""역대 선거 결과 페이지의 **정적 진입점** — 빈 상태를 시작점으로.

history.html은 '역대 선거 결과' 같은 검색어를 받는 허브인데, JS 없이는 설명 몇 줄과
"시도·시군구를 선택하면 …"만 있었다. 사용자에게는 막다른 화면이고 크롤러에게는
주제를 알 수 없는 페이지다. 둘은 같은 문제의 두 얼굴이다.

그래서 아무것도 고르지 않은 상태에 **실제 진입점**을 둔다:

    최근 선거 몇 개 → 각 아카이브로
    선거 종류별   → 대선·총선·지선 목록으로
    지역          → 지역 허브로

`선택하세요`가 아니라 `여기부터 보세요`다. 링크는 전부 표준 <a href>라 크롤러가
그대로 따라간다 — 이 페이지가 막다른 골목이 아니게 된다.

## 목록을 손으로 적지 않는다

data/elections/*.json에서 뽑는다. 새 회차를 넣으면 여기도 따라온다.

사용: python scripts/build/build_history_static.py
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "history.html"
START = "<!-- HS_STATIC_START"
END = "<!-- HS_STATIC_END -->"
R_START = "<!-- HS_ROUNDS_START"
R_END = "<!-- HS_ROUNDS_END -->"
KIND_LABEL = {"presidential": "대통령선거", "general_election": "국회의원선거",
              "local": "지방선거"}
KIND_HREF = {"presidential": "presidential", "general_election": "national_assembly",
             "local": "local"}
RECENT_N = 6


def esc(s) -> str:
    return (str(s if s is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def elections() -> list:
    out = []
    for f in sorted(glob.glob(str(ROOT / "data/elections/*.json"))):
        if f.endswith("index.json"):
            continue
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        if not isinstance(d, dict) or not d.get("date") or not d.get("name"):
            continue
        ar = d.get("archive") if isinstance(d.get("archive"), dict) else {}
        page = ar.get("page")
        if not page:
            continue
        out.append({"name": d["name"], "date": d["date"], "kind": d.get("kind"),
                    "page": page, "n": d.get("n")})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def block() -> str:
    els = elections()
    if not els:
        return START + " — 표시할 선거가 없다 -->\n" + END
    recent = els[:RECENT_N]
    kinds = []
    for k, label in KIND_LABEL.items():
        n = sum(1 for e in els if e["kind"] == k)
        if n:
            kinds.append((k, label, n))
    out = [START + " — scripts/build/build_history_static.py 자동 갱신. 손수정 X. -->",
           '  <section class="hs-start" aria-label="어디부터 볼까요">',
           '    <h2 class="hs-start-title">어디부터 볼까요</h2>',
           '    <div class="hs-start-group"><span class="hs-start-label">최근 선거</span>',
           '      <ul class="hs-start-list">']
    for e in recent:
        out.append(f'        <li><a href="{esc(e["page"])}">{esc(e["name"])}'
                   f'<span class="hs-date">{esc(e["date"])}</span></a></li>')
    out += ['      </ul>', '    </div>',
            '    <div class="hs-start-group"><span class="hs-start-label">선거 종류</span>',
            '      <ul class="hs-start-list hs-inline">']
    for k, label, n in kinds:
        out.append(f'        <li><a href="/history.html?type={KIND_HREF[k]}">'
                   f'{esc(label)}<span class="hs-date">{n}회</span></a></li>')
    out += ['      </ul>', '    </div>',
            '    <div class="hs-start-group"><span class="hs-start-label">지역으로</span>',
            '      <ul class="hs-start-list hs-inline">',
            '        <li><a href="/region/">지역별 선거 기록</a></li>',
            '        <li><a href="/timeline.html">역대 판세</a></li>',
            '        <li><a href="/elections.html">모든 선거</a></li>',
            '      </ul>', '    </div>', '  </section>', "  " + END]
    return "\n".join(out)


# ── 회차별 결과 지도 색인 ──────────────────────────────────────────────────
# /history/{종류}/{n}/[{직위}]/ 프리렌더 66쪽은 **서로만 링크하는 섬이었다.**
# 저장소 어디에도 이 66쪽을 정적으로 가리키는 페이지가 없어서, 크롤러가 들어갈
# 입구가 sitemap뿐이었다. 실제로 2026-08 URL Inspection에서 65쪽 중 41쪽이
# 'Google에 알려지지 않은 URL'로 나왔다 — 인물 1,820쪽이 겪은 것과 같은 구조다
# (4b10a4c0c). 그 66쪽이 회차별 결과 지도, 즉 이 사이트가 보여주려는 것 자체다.
#
# JS 타임라인이 같은 링크를 만들지만 렌더 후에만 존재한다. 사용자 도달 가능성과
# 크롤러 가시성은 다른 질문이다(page-map gap-2·gap-5의 교훈).
#
# 라벨은 페이지의 <h1>에서 읽는다. 여기서 다시 조립하면 build_static.py의 제목
# 규칙과 조용히 어긋난다 — 페이지가 자기 이름의 정본이다.

KIND_DIR = {"presidential": "대선", "national-assembly": "총선", "local": "지방선거"}


def rounds() -> dict:
    """{종류: [(정렬키, 경로, 라벨)]} — 파일 시스템이 정본. 생성된 것만 링크한다."""
    out: dict = {k: [] for k in KIND_DIR}
    for f in sorted(ROOT.glob("history/*/*/**/index.html")) + sorted(ROOT.glob("history/*/*/index.html")):
        rel = f.relative_to(ROOT)
        parts = rel.parts
        if len(parts) < 3 or parts[0] != "history":
            continue
        kind = parts[1]
        if kind not in KIND_DIR:
            continue
        try:
            n = int(parts[2])
        except ValueError:
            continue
        href = "/" + "/".join(parts[:-1]) + "/"
        if any(href == h for _, h, _ in out[kind]):
            continue
        m = re.search(r"<h1[^>]*>([^<]+)</h1>", f.read_text(encoding="utf-8"))
        if not m:
            continue
        out[kind].append(((n, href), href, m.group(1).strip()))
    for k in out:
        out[k].sort(key=lambda x: x[0], reverse=True)
    return out


def rounds_block() -> str:
    rs = rounds()
    total = sum(len(v) for v in rs.values())
    if not total:
        return R_START + " — 프리렌더가 없다 -->\n" + R_END
    out = [R_START + " — scripts/build/build_history_static.py 자동 갱신. 손수정 X.",
           "           JS 타임라인이 같은 링크를 만들지만 렌더 후에만 존재한다. -->",
           '  <section class="hs-start" aria-label="회차별 결과 지도">',
           f'    <h2 class="hs-start-title">회차별 결과 지도 <span class="hs-date">{total}회차</span></h2>']
    for kind, label in KIND_DIR.items():
        items = rs.get(kind) or []
        if not items:
            continue
        out += [f'    <div class="hs-start-group"><span class="hs-start-label">{esc(label)}</span>',
                '      <ul class="hs-start-list hs-inline">']
        for _, href, text in items:
            out.append(f'        <li><a href="{esc(href)}">{esc(text)}</a></li>')
        out += ['      </ul>', '    </div>']
    out += ['  </section>', "  " + R_END]
    return "\n".join(out)


def main() -> int:
    html = PAGE.read_text(encoding="utf-8")
    blk = block()
    if START in html:
        new = re.sub(re.escape(START) + r"[\s\S]*?" + re.escape(END), blk, html, count=1)
    else:
        # 빈 상태 안내 **앞**에 둔다 — JS가 뜨면 아래 지도가 본론이 되고,
        # 안 뜨면 이게 유일한 진입점이 된다.
        anchor = '  <footer class="foot">'
        if anchor not in html:
            print("ERR: history.html에 삽입 지점이 없다", file=sys.stderr)
            return 1
        new = html.replace(anchor, blk + "\n\n" + anchor, 1)
    # 회차별 색인 — HS_STATIC 바로 뒤에 둔다. 없으면 footer 앞.
    rblk = rounds_block()
    if R_START in new:
        new = re.sub(re.escape(R_START) + r"[\s\S]*?" + re.escape(R_END), rblk, new, count=1)
    else:
        anchor = "  " + END
        if anchor in new:
            new = new.replace(anchor, anchor + "\n\n" + rblk, 1)
        elif '  <footer class="foot">' in new:
            new = new.replace('  <footer class="foot">', rblk + "\n\n" + '  <footer class="foot">', 1)
        else:
            print("ERR: history.html에 회차 색인 삽입 지점이 없다", file=sys.stderr)
            return 1

    if new != html:
        PAGE.write_text(new, encoding="utf-8")
        print(f"→ history.html 진입점 갱신 (회차 색인 "
              f"{sum(len(v) for v in rounds().values())}개)", file=sys.stderr)
    else:
        print("→ 변경 없음", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
