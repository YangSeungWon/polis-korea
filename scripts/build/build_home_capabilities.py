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



# --- 미니 시각물 ---------------------------------------------------------------
# 능력 패널이 전부 '테두리 친 텍스트 상자'라 스크롤 리듬이 평평했다. 이 사이트의 언어는
# 지도·hex·막대인데 능력을 말로만 설명하고 있었다. 각 패널에 그 데이터의 실제 모양을
# 한 조각 넣는다 — 정확히 읽는 차트가 아니라 규모와 형태를 보여주는 텍스처다.
# 정확한 수치는 바로 아래 cap-figure에 숫자로 있으므로 그림만으로 값을 읽게 하지 않는다.
#
# 색은 쓰지 않는다(currentColor). 계열이 하나뿐이고, 여기에 정당색을 쓰면 있지도 않은
# 정파 의미가 생긴다. 라이트·다크는 상속색으로 자동 대응.

W, H = 168, 34


def _svg(inner: str, label: str) -> str:
    return (f'<svg class="cap-viz" viewBox="0 0 {W} {H}" preserveAspectRatio="none" '
            f'role="img" aria-label="{label}" focusable="false">{inner}</svg>')


def spark(vals: list, label: str) -> str:
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = W / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{H - 3 - (v - lo) / rng * (H - 8):.1f}"
                   for i, v in enumerate(vals))
    return _svg(f'<polyline points="{pts}" fill="none" stroke="currentColor" '
                f'stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>',
                label)


def bars(vals: list, label: str) -> str:
    if not vals:
        return ""
    hi = max(vals) or 1
    n = len(vals)
    gap = 2
    bw = (W - gap * (n - 1)) / n
    out = []
    for i, v in enumerate(vals):
        h = max(1.5, v / hi * (H - 4))
        out.append(f'<rect x="{i * (bw + gap):.1f}" y="{H - h:.1f}" width="{bw:.1f}" '
                   f'height="{h:.1f}" fill="currentColor" rx="1"/>')
    return _svg("".join(out), label)


def segments(widths: list, label: str) -> str:
    tot = sum(widths) or 1
    x = 0.0
    out = []
    for w in widths:
        ww = max(1.0, w / tot * W - 2)
        out.append(f'<rect x="{x:.1f}" y="{H / 2 - 5:.1f}" width="{ww:.1f}" height="10" '
                   f'fill="currentColor" rx="1"/>')
        x += w / tot * W
    return _svg("".join(out), label)


def viz_data() -> dict:
    """패널별 미니 시각물. 데이터가 없으면 그 패널만 그림 없이 나간다."""
    v = {}
    try:    # 국정지지율 시계열 — 갤럽 기록을 시간순으로
        rec = json.loads((ROOT / "data/polls/approval_gallup.json").read_text(encoding="utf-8"))
        rows = sorted((r for r in rec.get("records", []) if r.get("positive") is not None),
                      key=lambda r: r.get("period_start") or "")
        v["tracker"] = spark([r["positive"] for r in rows][-72:], "역대 국정지지율 추이")
    except Exception:
        pass
    try:    # 연도별 조사 건수
        from collections import Counter
        years = Counter()
        seen = set()
        for fp in (ROOT / "data/polls").glob("aggregated*.json"):
            if "scancache" in fp.name:
                continue
            d = json.loads(fp.read_text(encoding="utf-8"))
            polls = d.get("polls") if isinstance(d, dict) else d
            for p in polls or []:
                k, st = p.get("ntt_id"), (p.get("period_start") or "")
                if k and k not in seen and len(st) >= 4:
                    seen.add(k)
                    years[st[:4]] += 1
        ks = sorted(years)[-10:]
        v["poll"] = bars([years[k] for k in ks], "연도별 여론조사 건수")
    except Exception:
        pass
    try:    # 연대별 출마 건수
        from collections import Counter
        dec = Counter()
        for p in json.loads((ROOT / "assets/person-index.json").read_text(encoding="utf-8"))["persons"]:
            for r in p.get("races", []):
                y = r.get("year")
                if y:
                    dec[y // 10 * 10] += 1
        ks = sorted(dec)
        v["person"] = bars([dec[k] for k in ks], "연대별 출마 건수")
    except Exception:
        pass
    try:    # 공약 분야 분포 상위
        pl = json.loads((ROOT / "data/pledges/realm-summary.json").read_text(encoding="utf-8"))
        from collections import Counter
        tot = Counter()
        for e in pl.values():
            for r in e.get("realms", []):
                tot[r["realm"]] += r["n"]
        v["pledge"] = bars([n for _, n in tot.most_common(8)], "공약 분야 분포")
    except Exception:
        pass
    try:    # 계열별 정당 수
        from collections import Counter
        reg = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"]
        st = Counter(x.get("stream") or "기타" for x in reg.values())
        v["party"] = segments([n for _, n in st.most_common()], "계열별 정당 수")
    except Exception:
        pass
    try:    # 공화국 존속 기간
        h = json.loads((ROOT / "data/history_events.json").read_text(encoding="utf-8"))
        reps = [r for r in h.get("republics", []) if r.get("start")]
        yrs = [int(r["start"][:4]) for r in reps] + [2026]
        v["history"] = segments([max(1, yrs[i + 1] - yrs[i]) for i in range(len(yrs) - 1)],
                                "공화국별 존속 기간")
    except Exception:
        pass
    return v


def panel(href: str, title: str, sub: str, figure: str, more: str, viz: str = "") -> str:
    return (f'      <a class="dash-panel cap-panel" href="{href}">\n'
            f'        <h2>{title}</h2>\n'
            f'        <div class="dash-sub">{sub}</div>\n'
            f'        {viz}\n'
            f'        <div class="cap-figure">{figure}</div>\n'
            f'        <span class="dash-more">{more} →</span>\n'
            f'      </a>\n')


def build(c: dict) -> str:
    """능력 섹션 3개 × 2패널.

    이름은 사이트의 다른 곳과 같은 평서형 명사로 둔다 — '광역단체장'·'선거 타임라인'·
    '근현대사 연표' 옆에 수사의문문이 끼면 그 패널만 튄다.
    '역대 선거'는 바로 위 '역대' 섹션의 '역대 선거 결과'와 같은 것이라 넣지 않는다.
    """
    f = lambda n: f"{n:,}"
    v = viz_data()
    out = [START + " — scripts/build/build_home_capabilities.py 자동 갱신. 손수정 X. -->"]

    out.append('  <section class="dash-section">\n'
               '    <h2 class="dash-section-title">여론</h2>\n'
               '    <div class="dash-grid dash-grid-2">\n')
    out.append(panel("/tracker.html", "지지율 추이",
                     "대통령 국정평가·정당지지·차기주자를 선거와 무관하게 이어 본다",
                     "5개 조사기관 통합", "추이 보기", v.get("tracker", "")))
    out.append(panel("/polls.html", "여론조사",
                     "조사가 실제 결과를 얼마나 맞혔는지 회차별로 대조한다",
                     f"NESDC 등록 {f(c['poll'])}건", "조사 보기", v.get("poll", "")))
    out.append("    </div>\n  </section>\n")

    out.append('  <section class="dash-section">\n'
               '    <h2 class="dash-section-title">사람</h2>\n'
               '    <div class="dash-grid dash-grid-2">\n')
    out.append(panel("/search.html", "출마 이력",
                     "한 사람이 언제 어디서 무엇으로 나왔고 어떻게 됐는지",
                     f"{f(c['person'])}명", "이름으로 찾기", v.get("person", "")))
    if c["pledge"]:
        out.append(panel("/archive/9th-local-2026/", "선거공약",
                         "대통령·시도지사·시장군수구청장·교육감이 낸 공약서 원문. 낙선자 것까지",
                         f"{f(c['pledge'])}건 · {f(c['pledge_people'])}명", "분야별로 보기", v.get("pledge", "")))
    else:
        out.append(panel("/parties.html", "정당사",
                         "창당·합당·분당·해산으로 이어지는 계보",
                         f"정당 {f(c['party'])}개", "계보 보기", v.get("party", "")))
    out.append("    </div>\n  </section>\n")

    out.append('  <section class="dash-section">\n'
               '    <h2 class="dash-section-title">맥락</h2>\n'
               '    <div class="dash-grid dash-grid-2">\n')
    out.append(panel("/parties.html", "정당사",
                     "창당·합당·분당·해산으로 이어지는 계보",
                     f"정당 {f(c['party'])}개", "계보 보기", v.get("party", "")))
    out.append(panel("/chronology.html", "근현대사 연표",
                     "공화국·개헌·항쟁·정변과 모든 선거를 한 줄에 놓고 본다",
                     f"{c['republic']}개 공화국 · 주요 사건 {c['event']}건", "연표 보기", v.get("history", "")))
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
