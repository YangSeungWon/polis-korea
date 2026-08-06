"""지역 정치사 타임라인 정적 렌더러.

시간축은 **실제 날짜 비례**다. 1948~2026을 한 화면 폭에 우겨 넣으면 2020·2022·2024가
겹쳐 최근 정치사가 뭉개진다. px/year를 고정하고 가로로 탐색한다 — 19년은 실제로 길고
2년은 실제로 짧다.

세 객체를 따로 그린다.

    timeline_point     선거가 있었다는 사실
    comparison_edge    수치를 이어도 되는가 — 같은 series 안에서만
    historical_event   행정구역(전체 lane) · 선거구(관련 lane만)

**비교 불가 ≠ 역사에서 사라짐.** 부천 2016↔2020은 광역동이 선거구를 가로질러 delta를
못 내지만 점은 둘 다 남고 선만 끊긴다.

색 문법: 계열은 고유색, `mixed`는 중립+빗금(계열이 아니라 **상태**라서 고유 hue를 주면
'중도'로 오해된다), `unknown`은 옅은 중립, 무소속은 또 다른 범주다.
"""
from __future__ import annotations
import json, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/region_timeline"
OUT = ROOT / "region-timeline"
PXY = 26                      # 1년 = 26px. 이게 시간 비례의 전부다.
LANE_H, PAD_L, PAD_T = 34, 150, 56

SERIES_LABEL = {
    "president:national": "대통령", "general:district": "국회의원",
    "general:pr": "국회의원 비례", "local:metro_mayor": "광역단체장",
    "local:municipal_mayor": "기초단체장", "local:metro_council_district": "광역의원",
    "local:municipal_council_district": "기초의원",
    "local:metro_council_pr": "광역의원 비례",
    "local:municipal_council_pr": "기초의원 비례",
    "local:education_superintendent": "교육감", "byelection:unknown": "재·보궐",
}
# 상단 4개는 항상 펼친다. 나머지는 접는다 — 데이터에는 다 있고 UI만 감춘다.
PRIMARY = ["president:national", "general:district", "local:metro_mayor",
           "local:municipal_mayor"]
FAM_LABEL = {"conservative": "보수계", "democratic": "민주계",
             "progressive": "진보계", "regional": "지역계", "other": "기타",
             "mixed": "혼합 계보", "unknown": "계보 미확인", "independent": "무소속"}
FAM_COLOR = {"conservative": "#d2352b", "democratic": "#0a5cb8",
             "progressive": "#e8a300", "regional": "#00875a", "other": "#7a5cc0"}


def esc(s) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def yr(d: str) -> float:
    y, m, dd = (list(map(int, d.split("-"))) + [1, 1])[:3]
    return y + (date(y, m, dd).timetuple().tm_yday - 1) / 365.25


def render(doc: dict) -> str:
    pts, edges, evs = doc["points"], doc["comparison_edges"], doc.get("events") or []
    ys = [yr(p["election_date"]) for p in pts]
    y0, y1 = min(ys) - 1.5, max(ys) + 1.5
    W = PAD_L + (y1 - y0) * PXY + 40
    ser = [s for s in PRIMARY if s in doc["series"]] + \
          [s for s in doc["series"] if s not in PRIMARY]
    lane = {s: i for i, s in enumerate(ser)}
    H = PAD_T + len(ser) * LANE_H + 30
    x = lambda d: PAD_L + (yr(d) - y0) * PXY          # noqa: E731
    yl = lambda s: PAD_T + lane[s] * LANE_H + LANE_H / 2   # noqa: E731

    out = [f'<svg class="rt-svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" '
           f'height="{H:.0f}" role="img" aria-label="{esc(doc["region"])} 지역 정치사 연표">']
    # 연도 눈금 — 10년마다
    for y in range(int(y0) // 10 * 10, int(y1) + 10, 10):
        if y0 <= y <= y1:
            px = PAD_L + (y - y0) * PXY
            out.append(f'<line x1="{px:.0f}" y1="{PAD_T-14}" x2="{px:.0f}" y2="{H-24}" '
                       f'class="rt-grid"/><text x="{px:.0f}" y="{PAD_T-20}" '
                       f'class="rt-yr">{y}</text>')
    # lane 라벨·선
    for s in ser:
        out.append(f'<line x1="{PAD_L}" y1="{yl(s):.0f}" x2="{W-40:.0f}" '
                   f'y2="{yl(s):.0f}" class="rt-lane"/>'
                   f'<text x="{PAD_L-10}" y="{yl(s)+4:.0f}" class="rt-lab" '
                   f'text-anchor="end">{esc(SERIES_LABEL.get(s, s))}</text>')
    # 사건 — 행정구역은 전체를 가로지르고, 선거구는 관련 lane에만
    for e in evs:
        d = e.get("effective_date")
        if not d or not (y0 <= yr(d) <= y1):
            continue
        px = x(d)
        if e["namespace"] == "administrative_geography":
            out.append(f'<line x1="{px:.0f}" y1="{PAD_T-8}" x2="{px:.0f}" y2="{H-26}" '
                       f'class="rt-ev rt-ev-admin"><title>{esc(e["label"])}</title></line>'
                       f'<text x="{px+4:.0f}" y="{H-12}" class="rt-evlab">'
                       f'{esc(e["label"])}</text>')
        else:
            for s in e.get("affects_series") or []:
                if s in lane:
                    out.append(f'<line x1="{px:.0f}" y1="{yl(s)-13:.0f}" x2="{px:.0f}" '
                               f'y2="{yl(s)+13:.0f}" class="rt-ev rt-ev-dist">'
                               f'<title>{esc(e["label"])}</title></line>')
    # 비교선 — 점과 별개 객체. 차단이면 점선 + × 표시.
    for ed in edges:
        if ed["series"] not in lane:
            continue
        yy, a, b = yl(ed["series"]), x(ed["from_date"]), x(ed["to_date"])
        cls = ("rt-edge-ok" if ed["delta_allowed"] else
               "rt-edge-blocked" if ed["delta_allowed"] is False else "rt-edge-none")
        t = (f'변화량 비교 가능 · {ed.get("measurement_scope") or ""}'
             if ed["delta_allowed"] else
             f'변화량 비교 불가 — {ed.get("blocked_reason") or "판정 없음"}')
        out.append(f'<line x1="{a:.0f}" y1="{yy:.0f}" x2="{b:.0f}" y2="{yy:.0f}" '
                   f'class="{cls}"><title>{esc(t)}</title></line>')
        if ed["delta_allowed"] is False:
            m = (a + b) / 2
            out.append(f'<text x="{m:.0f}" y="{yy-6:.0f}" class="rt-x" '
                       f'text-anchor="middle">×</text>')
    # 한 지역에 같은 회차 선거구가 여럿일 수 있다(부천시갑·을·병). 같은 (날짜, lane)에
    # 그대로 찍으면 완전히 겹쳐 하나로 보인다. **x는 시간이라 못 옮기므로 y로 편다.**
    slot: dict = {}
    for p in sorted(pts, key=lambda q: (q["election_date"], q["unit_name_at_the_time"])):
        k = (p["election_date"], p["comparison_series_id"])
        slot[k] = slot.get(k, 0) + 1
        p["_slot"] = slot[k] - 1
    nslot = {k: v for k, v in slot.items()}

    # 점 — 계보 구성의 최다 bucket으로 칠한다. mixed는 빗금, unknown은 옅게.
    for p in pts:
        s = p["comparison_series_id"]
        if s not in lane:
            continue
        c = p.get("lineage_composition") or {}
        sh = c.get("share") or {}
        top = max(sh, key=sh.get) if sh else "unknown"
        fill = FAM_COLOR.get(top, "#8a8f98")
        cls = "rt-pt" + (" rt-pt-mixed" if top == "mixed" else
                         " rt-pt-unknown" if top in ("unknown", "independent") else "")
        comp = " · ".join(f"{FAM_LABEL.get(k, k)} {v}%"
                          for k, v in sorted(sh.items(), key=lambda i: -i[1]))
        mc = c.get("mixed_constituents") or {}
        mx = ("\n혼합 구성: " + ", ".join(
            f"{k}={'+'.join(FAM_LABEL.get(f, f) for f in v)}" for k, v in mc.items())
            if mc else "")
        w = p.get("winner") or {}
        cm = p.get("comparison") or {}
        claim = ""
        if cm:
            if cm.get("may_show_delta") and cm.get("delta"):
                claim = ("\n변화량(동 귀속표 기준): " +
                         ", ".join(f"{k.replace('pid:', '')} {v:+}%p"
                                   for k, v in cm["delta"].items()))
            if not cm.get("may_show_level"):
                claim += "\n※ 과거 재집계 수준값·승자는 사용하지 않음"
        # 이름이 같아도 다른 단위일 수 있다 — 1992 '포항시'와 1996 '포항시'는
        # 1995 도농통합 전후라 다른 entity다. version을 같이 보여준다.
        gv = p.get("geography_version_id")
        gtxt = (f'\n당시 행정구역: {gv.split(":")[-1]} ({gv})' if gv else
                '\n당시 행정구역 연결 정보 미등록')
        title = (f'{p["label"]}\n당시 선거구: {p["unit_name_at_the_time"]}{gtxt}\n'
                 f'당선: {w.get("party") or ""} {w.get("name") or ""} {w.get("pct") or ""}%\n'
                 f'계보 구성: {comp}{mx}{claim}')
        n = nslot[(p["election_date"], s)]
        # 넷 이상이 한 자리에 몰리면 펴도 서로 겹친다(기초의원은 한 지역에 6~10개).
        # 억지로 펴서 읽을 수 없게 만드는 대신 **하나로 묶고 개수를 밝힌다** —
        # 데이터는 그대로 있고 화면만 접는다.
        if n > 3:
            if p["_slot"] > 0:
                continue
            grouped = [q for q in pts
                       if q["election_date"] == p["election_date"]
                       and q["comparison_series_id"] == s]
            names = ", ".join(q["unit_name_at_the_time"] for q in grouped)
            lab = (f'{p["label"]} · {SERIES_LABEL.get(s, s)} {n}개 선거구\n{names}\n'
                   f'개별 결과는 목록에서 볼 수 있습니다')
            out.append(f'<circle cx="{x(p["election_date"]):.0f}" cy="{yl(s):.0f}" '
                       f'r="8" class="rt-pt rt-pt-group" fill="{fill}" tabindex="0" '
                       f'role="img" aria-label="{esc(lab.replace(chr(10), " / "))}">'
                       f'<title>{esc(lab)}</title></circle>'
                       f'<text x="{x(p["election_date"]):.0f}" y="{yl(s)+3:.0f}" '
                       f'class="rt-cnt" text-anchor="middle">{n}</text>')
            continue
        r = 6 if n == 1 else 5
        off = 0 if n == 1 else (p["_slot"] - (n - 1) / 2) * 11
        out.append(f'<circle cx="{x(p["election_date"]):.0f}" '
                   f'cy="{yl(s) + off:.0f}" r="{r}" '
                   f'class="{cls}" fill="{fill}" tabindex="0" role="img" '
                   f'aria-label="{esc(title.replace(chr(10), " / "))}">'
                   f'<title>{esc(title)}</title></circle>')
    out.append("</svg>")
    return "\n".join(out)


STYLE = """<style>
.rt-wrap{--rt-ink:#1a1d21;--rt-mut:#6b7280;--rt-line:#d7dbe0;--rt-bg:#fff}
@media(prefers-color-scheme:dark){.rt-wrap{--rt-ink:#e7e9ec;--rt-mut:#9aa1ab;
 --rt-line:#3a4048;--rt-bg:#14171a}}
:root[data-theme=dark] .rt-wrap{--rt-ink:#e7e9ec;--rt-mut:#9aa1ab;--rt-line:#3a4048;
 --rt-bg:#14171a}
:root[data-theme=light] .rt-wrap{--rt-ink:#1a1d21;--rt-mut:#6b7280;--rt-line:#d7dbe0;
 --rt-bg:#fff}
.rt-wrap{color:var(--rt-ink)}
.rt-note,.rt-meta,.rt-legend{color:var(--rt-mut);font-size:.86rem;line-height:1.6}
/* 긴 연표는 가로로 탐색한다 — 폭에 우겨 넣으면 최근 선거가 겹친다 */
.rt-scroll{overflow-x:auto;overflow-y:hidden;max-width:100%;
 border:1px solid var(--rt-line);border-radius:8px;background:var(--rt-bg)}
.rt-svg{display:block}
.rt-grid{stroke:var(--rt-line);stroke-width:1;stroke-dasharray:2 4}
.rt-lane{stroke:var(--rt-line);stroke-width:1}
.rt-lab,.rt-yr{fill:var(--rt-mut);font-size:11px}
.rt-lab{font-size:12px;fill:var(--rt-ink)}
.rt-edge-ok{stroke:var(--rt-ink);stroke-width:2;opacity:.35}
/* 비교 불가 — 선만 끊긴다. 점은 그대로 남는다. */
.rt-edge-blocked{stroke:var(--rt-mut);stroke-width:1.5;stroke-dasharray:3 4;opacity:.5}
.rt-edge-none{stroke:var(--rt-line);stroke-width:1;opacity:.35}
.rt-x{fill:var(--rt-mut);font-size:12px;font-weight:700}
.rt-pt{stroke:var(--rt-bg);stroke-width:1.5;cursor:default}
.rt-pt:focus{outline:2px solid var(--rt-ink);outline-offset:2px}
/* mixed는 계열이 아니라 상태다 — 고유 hue를 주면 '중도'로 오해된다 */
.rt-pt-mixed{fill:var(--rt-mut)!important;stroke-dasharray:2 2;stroke:var(--rt-ink)}
.rt-pt-unknown{opacity:.4}
.rt-pt-group{stroke-width:2}
.rt-cnt{fill:#fff;font-size:9px;font-weight:700;pointer-events:none}
.rt-ev{stroke-width:1.5}
.rt-ev-admin{stroke:var(--rt-ink);stroke-dasharray:5 3;opacity:.55}
.rt-ev-dist{stroke:var(--rt-mut);stroke-dasharray:2 2}
.rt-evlab{fill:var(--rt-mut);font-size:10px}
.rt-key{display:inline-flex;align-items:center;gap:.3em;margin-right:.9em}
.rt-key i{width:11px;height:11px;border-radius:50%;display:inline-block}
.rt-i-mixed{background:var(--rt-mut);border:1.5px dashed var(--rt-ink)}
.rt-i-unknown{background:var(--rt-mut);opacity:.4}
</style>"""

PAGE = """<section class="rt-wrap">
<h2>{region} 지역 정치사</h2>
<p class="rt-note">가로축은 <b>실제 날짜 비례</b>입니다 — 긴 공백은 실제로 깁니다.
점은 선거, 선은 <b>변화량을 이어도 되는지</b>를 뜻합니다.
<span class="rt-x">×</span> 는 선거는 있었지만 경계·구도가 달라 변화량을 비교할 수 없다는
뜻이지 결과가 없다는 뜻이 아닙니다.</p>
<div class="rt-scroll">{svg}</div>
<p class="rt-legend">{legend}</p>
<p class="rt-meta">{meta}</p>
</section>"""


def main(regions: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for f in sorted(SRC.glob("*.json")):
        if regions and f.stem not in regions:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        leg = " ".join(
            f'<span class="rt-key"><i style="background:{c}"></i>{FAM_LABEL[k]}</span>'
            for k, c in FAM_COLOR.items() if k != "other")
        leg += ('<span class="rt-key"><i class="rt-i-mixed"></i>혼합 계보</span>'
                '<span class="rt-key"><i class="rt-i-unknown"></i>계보 미확인·무소속</span>')
        bd = d.get("bridge_dependency") or {}
        share = bd.get("bridge_dependent_share_of_resolved")
        meta = (f'선거 {len(d["points"])}회 · 계열 {len(d["series"])}종 · '
                f'행정구역·선거구 사건 {len(d.get("events") or [])}건')
        if share is not None:
            meta += (f' · 계보 분류의 {share}%는 강제해산 등 제도적 단절을 '
                     f'건너는 역사적 연속성 해석에 기댑니다')
        # STYLE은 format 대상이 아니다 — CSS의 중괄호가 .format()과 충돌한다
        body = PAGE.format(region=esc(d["region"]), svg=render(d),
                           legend=leg, meta=esc(meta))
        # 감사·미리보기용 독립 문서. 실제 사이트에 얹을 땐 body만 쓴다.
        html = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<meta name="robots" content="noindex">'
                f'<title>{esc(d["region"])} 지역 정치사</title>{STYLE}</head>'
                f'<body>{body}</body></html>')
        (OUT / f"{f.stem}.html").write_text(html, encoding="utf-8")
        print(f"  {d['region']}: lane {len(d['series'])} · 점 {len(d['points'])} · "
              f"선 {len(d['comparison_edges'])}")
    print(f"\n→ {OUT.name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
