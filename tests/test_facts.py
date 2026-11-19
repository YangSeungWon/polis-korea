"""틀린 사실 회귀 검사 — 전수조사(2026-11)에서 찾은 거짓 문장이 다시 생기지 않는가.

막는 사고(전부 실제로 있었다):
  · 정당 출마 기록이 대선 시도 분해 행까지 세어 후보 1명이 '후보 18', 득표 2배.
  · 교육감 1위가 '무소속'으로 적혀 지역 요약이 '1위 정당 무소속'이 된다.
  · 지역 페이지가 없는 총선 기록을 '대선·총선·지선'으로 약속한다.
  · '2026~2026년'.
  · 인물 페이지에 원자료 slug('9 byelection'), 소속 정당이 앞 3개에서 잘려 지금 소속이 빠진다.
  · 정당 페이지에 큐레이터 메모(dissolved·노드·관측·**)가 그대로 나간다.
  · 1952년 아카이브에 여론조사심의위원회 링크·'18:00 발표' 출구조사 문구.
  · 역대 선거 색인이 페이지 수(66)를 회차 수로 쓴다.
  · 홈 '9개 공화국'(임시정부·미군정·군정까지 셈).

실행: .venv/bin/python tests/test_facts.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "build"))
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def main() -> int:
    print("\n[정당 출마 기록]")
    from build_party_pages import build_runs, public_note, race_level  # noqa: E402
    doc = json.loads(read(ROOT / "data/results/21st-pres-2025.json"))
    kept = race_level(doc)["races"]
    ck("대선은 전국 행만 센다", [(r["sg_typecode"], r["scope"]) for r in kept] == [("1", "nation")],
       str({(r["sg_typecode"], r["scope"]) for r in kept}))
    runs = build_runs()
    for party in ("국민의힘", "더불어민주당"):
        r = next((x for x in runs.get(party, []) if x["date"] == "2025-06-03"), None)
        ck(f"{party} 21대 대선 후보 1명·당선 ≤1", bool(r) and r["candidates"] == 1 and r["won"] <= 1, str(r))
    loc = json.loads(read(ROOT / "data/results/9th-local-2026.json"))
    scopes = {r["scope"] for r in race_level(loc)["races"]}
    ck("지선 분해 행(_sigungu·_part)은 빠진다", not any(s.endswith(("_sigungu", "_part")) for s in scopes), str(scopes))
    ck("지선 광역단체장 시군구 분해 행도 빠진다",
       not any(r["sg_typecode"] == "3" and r["scope"] == "sigungu" for r in race_level(loc)["races"]))

    print("\n[정당 메모]")
    bad = re.compile(r"dissolved|founded|successors|predecessors|absorbed|노드|edge|관측|\*\*|※")
    leaked = []
    for f in sorted((ROOT / "party").glob("*/index.html")):
        m = re.search(r'<p class="pty-note">([^<]*)', read(f))
        if m and bad.search(m.group(1)):
            leaked.append(f.parent.name)
    ck("큐레이터 메모가 정당 페이지에 새지 않는다", not leaked, ", ".join(leaked[:5]))
    ck("메모의 사실 문장은 남긴다", "노회찬" in public_note("통진당 분당. 노회찬·심상정. ※한시 당명은 노드에서."))

    print("\n[지역 페이지]")
    pages = sorted((ROOT / "region").glob("*/index.html"))
    ck("지역 페이지가 있다", len(pages) > 300, str(len(pages)))
    total_claim, same_year, mu_lede = [], [], []
    for f in pages:
        h = read(f)
        head = h.split("</head>")[0]
        if "총선" in head:
            total_claim.append(f.parent.name)
        if re.search(r"(\d{4})~\1년", h):
            same_year.append(f.parent.name)
        m = re.search(r'<p class="rg-lede">([^<]*)', h) or re.search(r'class="lede"[^>]*>([^<]*)', h)
        if m and "1위 정당 무소속" in m.group(1):
            mu_lede.append(f.parent.name)
    ck("총선 기록이 없는데 '총선'을 약속하지 않는다", not total_claim, ", ".join(total_claim[:5]))
    ck("'2026~2026년' 같은 같은 해 범위가 없다", not same_year, ", ".join(same_year[:5]))
    rows = json.loads(read(next((ROOT / "data/regions").glob("경기도-성남시*.json"))))
    rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
    edu = [r for r in rows if isinstance(r, dict) and r.get("office") == "교육감"]
    ck("교육감 행은 정당이 없다(null)", edu and all(r.get("party") is None for r in edu), str(edu[:1]))

    print("\n[인물 페이지]")
    raw = [f.parent.name for f in (ROOT / "person").glob("*/index.html")
           if re.search(r">\d+ byelection<", read(f))]
    ck("원자료 slug('9 byelection')가 보이지 않는다", not raw, ", ".join(raw[:5]))
    lee = next((ROOT / "person").glob("이재명-1964*/index.html"))
    desc = re.search(r'name="description" content="([^"]*)', read(lee)).group(1)
    ck("소속 요약에 지금 소속(더불어민주당)", "더불어민주당" in desc, desc)
    ck("꼬리말이 본문(낙선 기록)과 어긋나지 않는다", "비의원·낙선 이력은" not in read(lee))

    print("\n[아카이브]")
    a52 = read(ROOT / "archive/2nd-pres-1952/index.html")
    ck("1952년에 여론조사심의위원회 링크 없음", "nesdc.go.kr" not in a52)
    ck("회차와 무관한 '18:00 발표' 출구조사 문구 없음", "18:00 발표" not in a52)
    ck("1952년 설명이 여론조사·출구조사를 약속하지 않는다", "출구조사 비교" not in a52.split("</head>")[0])
    a21 = read(ROOT / "archive/21st-pres-2025/index.html")
    ck("여론조사가 있는 회차는 링크를 둔다", "nesdc.go.kr" in a21)

    print("\n[역대 선거·홈]")
    hist = read(ROOT / "history.html")
    m = re.search(r'회차별 결과 지도 <span class="hs-date">(\d+)회차', hist)
    pres = len(list((ROOT / "history/presidential").glob("*/index.html")))
    gen = len(list((ROOT / "history/national-assembly").glob("*/index.html")))
    loc_n = len([d for d in (ROOT / "history/local").iterdir() if d.is_dir()])
    ck("회차 수 = 대선+총선+지선 회차(페이지 수 아님)", m and int(m.group(1)) == pres + gen + loc_n,
       f"{m and m.group(1)} vs {pres}+{gen}+{loc_n}")
    home = read(ROOT / "index.html")
    ev = json.loads(read(ROOT / "data/history_events.json"))
    n_rep = sum(1 for r in ev["republics"] if "공화국" in r["name"])
    ck(f"홈 공화국 수 = {n_rep}", f"{n_rep}개 공화국" in home)
    ck("홈에 '17개 시·도' 없음(9회 지선은 16)", "17개 시·도" not in home)

    print(f"\n{'전부 통과' if not fails else f'실패 {len(fails)}'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
