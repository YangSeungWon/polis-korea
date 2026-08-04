"""홈의 '무엇을 볼 수 있나' 블록 생성 — index.html의 CAPS_START/END 사이를 갱신.

홈이 선거 결과 중심이라 여론·인물·정당·공약·근현대사가 nav에만 있었다. 스크롤을 내리면
사이트가 무엇을 줄 수 있는지 순서대로 드러나게 한다.

각 패널은 '무엇을 할 수 있는지' 한 줄 + **실제 수치**를 함께 낸다. 수치를 손으로 적으면
데이터가 늘 때마다 어긋나므로(오늘 nav에서 겪은 그대로) 데이터에서 세어 넣는다.
과장하지 않는다 — 여론조사는 파일 합계(10,939)가 아니라 NESDC 등록번호 기준 고유 건수를
쓴다. 같은 조사가 직위·지표별로 여러 행으로 갈리기 때문이다.

사용: python3 scripts/build/build_home_capabilities.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "index.html"
START = "<!-- CAPS_START"
END = "<!-- CAPS_END -->"


def counts() -> dict:
    c: dict[str, int] = {}
    c["person"] = len(list((ROOT / "person").glob("*/index.html")))
    c["party"] = len(list((ROOT / "party").glob("*/index.html")))
    c["archive"] = len(list((ROOT / "archive").glob("*/index.html")))

    ids = set()
    for fp in (ROOT / "data/polls").glob("aggregated*.json"):
        if "scancache" in fp.name:
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        polls = d.get("polls") if isinstance(d, dict) else d
        if isinstance(polls, list):
            ids.update(str(p["ntt_id"]) for p in polls if p.get("ntt_id"))
    c["poll"] = len(ids)

    try:
        pl = json.loads((ROOT / "data/pledges/realm-summary.json").read_text(encoding="utf-8"))
        c["pledge"] = sum(v.get("n_pledges", 0) for v in pl.values())
        c["pledge_rounds"] = len(pl)
    except Exception:
        c["pledge"] = c["pledge_rounds"] = 0
    try:
        idx = json.loads((ROOT / "assets/pledges-index.json").read_text(encoding="utf-8"))
        c["pledge_people"] = len(idx)
    except Exception:
        c["pledge_people"] = 0
    try:
        h = json.loads((ROOT / "data/history_events.json").read_text(encoding="utf-8"))
        c["event"] = len(h.get("events") or [])
        c["republic"] = len(h.get("republics") or [])
    except Exception:
        c["event"] = c["republic"] = 0
    try:
        el = json.loads((ROOT / "data/elections.json").read_text(encoding="utf-8"))
        c["election"] = sum(len(el[k]["elections"])
                            for k in ("presidential", "national_assembly", "local"))
    except Exception:
        c["election"] = 0
    return c


def panel(href: str, title: str, sub: str, figure: str, more: str) -> str:
    return (f'      <a class="dash-panel cap-panel" href="{href}">\n'
            f'        <h2>{title}</h2>\n'
            f'        <div class="dash-sub">{sub}</div>\n'
            f'        <div class="cap-figure">{figure}</div>\n'
            f'        <span class="dash-more">{more} →</span>\n'
            f'      </a>\n')


def build(c: dict) -> str:
    f = lambda n: f"{n:,}"
    out = [START + " — scripts/build/build_home_capabilities.py 자동 갱신. 손수정 X. -->"]

    out.append('  <section class="dash-section">\n'
               '    <h2 class="dash-section-title">여론</h2>\n'
               '    <div class="dash-grid dash-grid-2">\n')
    out.append(panel("/tracker.html", "지지율 추이",
                     "대통령 국정평가·정당지지·차기주자를 선거와 무관하게 이어 본다",
                     "5개 조사기관 통합", "추이 보기"))
    out.append(panel("/polls.html", "여론조사",
                     "조사가 실제 결과를 얼마나 맞혔는지 회차별로 대조한다",
                     f"NESDC 등록 {f(c['poll'])}건", "조사 보기"))
    out.append("    </div>\n  </section>\n")

    out.append('  <section class="dash-section">\n'
               '    <h2 class="dash-section-title">사람과 정당</h2>\n'
               '    <div class="dash-grid dash-grid-2">\n')
    out.append(panel("/search.html", "인물",
                     "한 사람이 언제 어디서 무엇으로 나왔고 어떻게 됐는지",
                     f"{f(c['person'])}명", "이름으로 찾기"))
    out.append(panel("/parties.html", "정당사",
                     "창당·합당·분당·해산으로 이어지는 계보",
                     f"정당 {f(c['party'])}개", "계보 보기"))
    out.append("    </div>\n  </section>\n")

    if c["pledge"]:
        out.append('  <section class="dash-section">\n'
                   '    <h2 class="dash-section-title">공약</h2>\n'
                   '    <div class="dash-grid dash-grid-2">\n')
        out.append(panel("/archive/9th-local-2026/", "무엇을 약속했나",
                         "대통령·시도지사·시장군수구청장·교육감의 선거공약서 원문",
                         f"{f(c['pledge'])}건 · {f(c['pledge_people'])}명", "9회 지선에서 보기"))
        out.append(panel("/search.html", "누가 약속했나",
                         "당선인뿐 아니라 낙선자 공약까지 — 사라지기 전에 받아 둔 것",
                         f"{c['pledge_rounds']}개 회차", "인물에서 보기"))
        out.append("    </div>\n  </section>\n")

    out.append('  <section class="dash-section">\n'
               '    <h2 class="dash-section-title">역사</h2>\n'
               '    <div class="dash-grid dash-grid-2">\n')
    out.append(panel("/chronology.html", "근현대사 연표",
                     "공화국·개헌·항쟁·정변과 모든 선거를 한 줄에 놓고 본다",
                     f"{c['republic']}개 공화국 · 주요 사건 {c['event']}건", "연표 보기"))
    out.append(panel("/history.html", "역대 선거",
                     "1948년 제헌부터 지금까지, 지역별로 어떻게 갈렸나",
                     f"{f(c['election'])}회 · 아카이브 {c['archive']}건", "결과 보기"))
    out.append("    </div>\n  </section>\n")

    out.append("  " + END)
    return "\n".join(out)


def main():
    if not INDEX.exists():
        print("ERR: index.html 없음", file=sys.stderr)
        sys.exit(1)
    html = INDEX.read_text(encoding="utf-8")
    if START not in html:
        print("ERR: index.html에 CAPS_START 마커가 없다", file=sys.stderr)
        sys.exit(1)
    c = counts()
    block = build(c)
    new = re.sub(re.escape(START) + r"[\s\S]*?" + re.escape(END), block, html, count=1)
    if new != html:
        INDEX.write_text(new, encoding="utf-8")
        print("→ index.html 능력 블록 갱신", file=sys.stderr)
    else:
        print("→ 변경 없음", file=sys.stderr)
    print("   " + " · ".join(f"{k} {v:,}" for k, v in c.items()), file=sys.stderr)


if __name__ == "__main__":
    main()
