"""지도 타임랩스 정적 렌더러 — 다섯 상태를 **프레임으로** 그린다.

애니메이션이 아니다. 각 상태는 독립 프레임이고 그 사이를 보간하지 않는다.
1994-12-31 `포항시+영일군` → 1995-01-01 `포항시`는 딱 바뀐다 — 없던 중간 경계를
만들지 않는다.

세 가지를 화면에서도 섞지 않는다:

    경계        그 시점의 실제 polygon
    선거        고른 series의 snapshot
    투영        칠할 수 있는가 (direct/aggregated/reaggregated/unavailable)

`unavailable`은 폴리곤을 **그리되 정치색을 주지 않는다**. 색이 없는 것과 데이터가
없는 것은 다르고, 화면이 그 차이를 말해야 한다.

색 문법: 색 = 1위 계열, 강도 = 3단계(키 있음). `mixed`는 계열이 아니라 상태라
고유 hue 대신 중립+빗금이다 — hue를 주면 '중도'로 읽힌다.

사용: python scripts/build/render_map_timelapse.py [지역 ...]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from map_timelapse import _rings  # noqa: E402  (면적·좌표 해석을 한 곳에서)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/map_timelapse"
OUT = ROOT / "map-timelapse"

W, H, PAD = 520, 560, 18
FAM_COLOR = {"conservative": "#d2352b", "democratic": "#0a5cb8",
             "progressive": "#e8a300", "regional": "#00875a", "other": "#7a5cc0"}
FAM_LABEL = {"conservative": "보수계", "democratic": "민주계",
             "progressive": "진보계", "regional": "지역계", "other": "기타"}
SERIES_LABEL = {"president:national": "대통령", "general:district": "국회의원",
                "general:pr": "국회의원 비례", "local:metro_mayor": "광역단체장",
                "local:municipal_mayor": "기초단체장"}
METHOD_LABEL = {"direct": "그대로", "aggregated": "합산", "reaggregated": "재집계",
                "unavailable": "표시 불가"}
# 강도는 3단계로만. 연속 명도는 키 없이 읽을 수 없다.
STEPS = [(0, 45, "45% 미만", 0.42), (45, 60, "45–60%", 0.68), (60, 101, "60% 이상", 1.0)]


def esc(s) -> str:
    return (str(s if s is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def bbox(doc: dict) -> tuple:
    xs, ys = [], []
    for b in doc["series_blocks"]:
        for s in b["states"]:
            for f in s["geography_at_date"]["features"]:
                for ring in _rings(f["geometry"]):
                    for x, y in ring:
                        xs.append(x)
                        ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def projector(bb: tuple):
    """모든 프레임이 **같은 화면 좌표**를 쓴다 — 경계 변화가 재프레이밍으로 보이면 안 된다."""
    x0, y0, x1, y1 = bb
    k = math.cos(math.radians((y0 + y1) / 2))
    w, h = (x1 - x0) * k, y1 - y0
    sc = min((W - 2 * PAD) / w, (H - 2 * PAD) / h)
    ox = PAD + ((W - 2 * PAD) - w * sc) / 2
    oy = PAD + ((H - 2 * PAD) - h * sc) / 2

    def f(x, y):
        return (ox + (x - x0) * k * sc, oy + (y1 - y) * sc)
    return f


def label_at(g: dict, pr) -> tuple:
    """가장 큰 링의 무게중심. 폴리곤이 두 개면 이름이 어디 붙는지가 곧 식별이다."""
    ring = max(_rings(g), key=len)
    pts = [pr(x, y) for x, y in ring]
    return (sum(a for a, _ in pts) / len(pts), sum(b for _, b in pts) / len(pts))


def path_of(g: dict, pr) -> str:
    out = []
    for ring in _rings(g):
        pts = [pr(x, y) for x, y in ring]
        out.append("M" + "L".join(f"{a:.1f},{b:.1f}" for a, b in pts) + "Z")
    return "".join(out)


def fill_for(proj: dict) -> tuple:
    """(fill, extra-class, 설명). 투영이 색을 정한다 — 반대가 아니다."""
    if not proj or proj["method"] == "unavailable":
        return "url(#mt-none)", "mt-unavailable", "이 경계로 표시할 수 없음"
    p = proj.get("paint") or {}
    if p.get("state") == "family":
        c = FAM_COLOR[p["family"]]
        op = next(o for lo, hi, _, o in STEPS if lo <= p["share"] < hi)
        return c, f"mt-op{int(op * 100)}", f"{FAM_LABEL[p['family']]} {p['share']}%"
    if p.get("state") == "mixed":
        return "url(#mt-mixed)", "mt-mixed", f"복수 계보 {p.get('share', 0)}%"
    return "url(#mt-unknown)", "mt-unknown", {"unknown": "계보 미확인",
                                              "independent": "무소속"}.get(
        p.get("state"), "자료 없음")


def frame(s: dict, pr, sid: str, visible: bool = False) -> str:
    g, proj = s["geography_at_date"], s["political_projection"]
    snap = s["election_snapshot"]
    shapes, labels = [], []
    for f in g["features"]:
        p = proj["per_unit"].get(f["model_unit"])
        fill, cls, desc = fill_for(p)
        m = (p or {}).get("method", "unavailable")
        shapes.append(
            f'<path class="mt-u {cls}" fill="{fill}" d="{path_of(f["geometry"], pr)}"'
            f' role="img" aria-label="{esc(f["model_unit"])} — {esc(desc)},'
            f' 투영 {esc(METHOD_LABEL[m])}"><title>{esc(f["model_unit"])}'
            f'\n{esc(desc)}\n투영: {esc(METHOD_LABEL[m])}</title></path>')
    # 이름이 없으면 두 단위가 같은 채움일 때 한 덩어리로 읽힌다(하남 갑·을이 그랬다).
    seen = set()
    for f in g["features"]:
        if f["model_unit"] in seen:
            continue
        seen.add(f["model_unit"])
        lx, ly = label_at(f["geometry"], pr)
        labels.append(f'<text class="mt-lb" x="{lx:.0f}" y="{ly:.0f}" '
                      f'text-anchor="middle" aria-hidden="true">'
                      f'{esc(f["model_unit"])}</text>')
    rows = []
    for name, p in sorted(proj["per_unit"].items()):
        _, _, desc = fill_for(p)
        w = p.get("winner") or {}
        src = p.get("source_units") or []
        detail = (f'{esc(w.get("party"))} {esc(w.get("name"))} {w.get("pct")}%'
                  if w.get("name") else esc(p.get("why") or p.get("reason") or ""))
        # 사유는 길다. 좁은 칸에 밀어 넣으면 한글이 한 글자씩 끊긴다(실제로 그랬다).
        # 자기 줄을 준다.
        rows.append(
            f'<tr><th scope="row">{esc(name)}</th>'
            f'<td><span class="mt-b mt-b-{p["method"]}">{METHOD_LABEL[p["method"]]}'
            f'</span></td><td>{esc(desc)}</td><td class="mt-src">{detail if w.get("name") else ""}'
            + (f'<br><span class="mt-dim">집계 단위 {esc(" + ".join(src))}</span>'
               if len(src) > 1 else "")
            + '</td></tr>')
        note = p.get("why") or p.get("reason")
        if not w.get("name") and note:
            rows.append(f'<tr class="mt-why"><td colspan="4">{esc(note)}</td></tr>')
    ev = ('<p class="mt-ev">이 시점에 행정구역이 바뀌었습니다 — 경계는 사건일에 '
          '이산 전환하며, 없던 중간 경계를 만들지 않습니다.</p>'
          if s["role"] == "after_geo_event" else "")
    return f"""<section class="mt-frame" data-role="{esc(s['role'])}"
 data-series="{esc(sid)}" data-state="{esc(s['state_id'])}"{'' if visible else ' hidden'}>
<h3 class="mt-h">{esc(s['role_label'])} · {esc(s['date'])}</h3>
<div class="mt-grid">
<svg class="mt-svg" viewBox="0 0 {W} {H}" role="group"
 aria-label="{esc(s['date'])} 시점 경계 {esc(g['topology_signature'])}">{''.join(shapes)}
{''.join(labels)}</svg>
<div class="mt-side">
<p class="mt-claim">{esc(s['displayable_claim'])}</p>
{ev}
<dl class="mt-layers">
<dt>경계</dt><dd class="mt-geo">{esc(' · '.join(g['units']))}
 <span class="mt-dim">({esc(g['boundary_source'])})</span></dd>
<dt>선거</dt><dd class="mt-snap">{esc(snap['label'] if snap else '없음')}
 <span class="mt-dim">{esc(snap['date'] if snap else '')}</span></dd>
<dt>투영</dt><dd class="mt-proj">{esc(' · '.join(
    f'{METHOD_LABEL[k]} {v}곳' for k, v in sorted(proj['summary'].items())) or '없음')}</dd>
</dl>
<table class="mt-tab"><caption>단위별 투영</caption>
<colgroup><col class="c1"><col class="c2"><col class="c3"><col></colgroup>
<thead><tr><th>경계 단위</th>
<th>투영</th><th>계열</th><th>1위 / 사유</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</div></div></section>"""


DEFS = """<svg width="0" height="0" aria-hidden="true"><defs>
<pattern id="mt-mixed" width="7" height="7" patternUnits="userSpaceOnUse"
 patternTransform="rotate(45)"><rect width="7" height="7" fill="#9aa3ad"/>
<line x1="0" y1="0" x2="0" y2="7" stroke="#f6f7f9" stroke-width="2.5"/></pattern>
<pattern id="mt-unknown" width="6" height="6" patternUnits="userSpaceOnUse">
<rect width="6" height="6" fill="#d7dbe0"/><circle cx="3" cy="3" r="1" fill="#8b939c"/>
</pattern>
<pattern id="mt-none" width="8" height="8" patternUnits="userSpaceOnUse"
 patternTransform="rotate(135)"><rect width="8" height="8" fill="#eceef1"/>
<line x1="0" y1="0" x2="0" y2="8" stroke="#b9c0c8" stroke-width="1.5"/></pattern>
</defs></svg>"""

STYLE = """<style>
:root{--mt-ink:#14181d;--mt-dim:#5d6672;--mt-line:#d8dde3;--mt-bg:#fff;--mt-card:#f7f8fa}
@media (prefers-color-scheme:dark){:root{--mt-ink:#e8ecf1;--mt-dim:#9aa4b0;
--mt-line:#333c47;--mt-bg:#0f1317;--mt-card:#171c22}}
.mt{color:var(--mt-ink);background:var(--mt-bg);font:15px/1.6 system-ui,sans-serif;
padding:20px;max-width:1080px;margin:0 auto}
.mt h2{font-size:20px;margin:0 0 4px}
.mt .mt-lead{color:var(--mt-dim);margin:0 0 16px;font-size:14px}
.mt-ctl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 6px}
.mt-ctl label{font-size:13px;color:var(--mt-dim)}
.mt-seg{display:flex;flex-wrap:wrap;gap:4px}
.mt-seg button{font:inherit;font-size:13px;padding:5px 11px;border:1px solid var(--mt-line);
background:var(--mt-bg);color:var(--mt-ink);border-radius:999px;cursor:pointer}
.mt-seg button[aria-pressed=true]{background:var(--mt-ink);color:var(--mt-bg);
border-color:var(--mt-ink)}
.mt-seg button:focus-visible{outline:2px solid #0a5cb8;outline-offset:2px}
.mt-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.05fr);gap:18px;
align-items:start}
@media (max-width:820px){.mt-grid{grid-template-columns:1fr}}
.mt-svg{width:100%;height:auto;background:var(--mt-card);border-radius:8px;
border:1px solid var(--mt-line)}
.mt-u{stroke:var(--mt-bg);stroke-width:2.5}
.mt-lb{font:600 12px system-ui,sans-serif;fill:var(--mt-ink);paint-order:stroke;
stroke:var(--mt-card);stroke-width:3.5px;stroke-linejoin:round}
.mt-op42{fill-opacity:.42}.mt-op68{fill-opacity:.68}.mt-op100{fill-opacity:1}
.mt-unavailable{stroke:#98a1ab;stroke-dasharray:4 3}
.mt-h{font-size:15px;margin:14px 0 8px}
.mt-claim{font-weight:600;margin:0 0 8px}
.mt-ev{margin:0 0 10px;font-size:13px;color:var(--mt-dim);border-left:3px solid var(--mt-line);
padding-left:9px}
.mt-layers{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;margin:0 0 12px;
font-size:14px}
.mt-layers dt{color:var(--mt-dim);font-size:13px}
.mt-layers dd{margin:0}
.mt-dim{color:var(--mt-dim);font-size:12px}
.mt-tab{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed;
word-break:keep-all}
.mt-tab col.c1{width:27%}.mt-tab col.c2{width:19%}.mt-tab col.c3{width:26%}
.mt-why td{color:var(--mt-dim);font-size:12.5px;border-top:0;padding-top:0;
line-height:1.55}
.mt-tab caption{text-align:left;color:var(--mt-dim);font-size:12px;padding-bottom:4px}
.mt-tab th,.mt-tab td{text-align:left;padding:5px 6px;border-top:1px solid var(--mt-line);
vertical-align:top}
.mt-tab thead th{color:var(--mt-dim);font-weight:500;border-top:0}
.mt-b{display:inline-block;font-size:12px;padding:1px 7px;border-radius:999px;
border:1px solid var(--mt-line)}
.mt-b-direct{border-color:#2a7d4f;color:#2a7d4f}
.mt-b-aggregated{border-color:#8a6d1f;color:#8a6d1f}
.mt-b-unavailable{border-color:#98a1ab;color:var(--mt-dim)}
@media (prefers-color-scheme:dark){.mt-b-direct{border-color:#6fd39a;color:#6fd39a}
.mt-b-aggregated{border-color:#dcb54a;color:#dcb54a}}
.mt-key{display:inline-flex;align-items:center;gap:5px;margin-right:12px;font-size:12px;
color:var(--mt-dim)}
.mt-key i{width:13px;height:13px;border-radius:3px;display:inline-block;
border:1px solid var(--mt-line)}
.mt-legend{margin:12px 0 0;line-height:2}
.mt-note{color:var(--mt-dim);font-size:12.5px;margin:10px 0 0}
</style>"""

SCRIPT = """<script>
(function(){
 var root=document.querySelector('.mt'); if(!root) return;
 var st={series:root.dataset.series,role:root.dataset.role};
 function draw(){
  root.querySelectorAll('.mt-frame').forEach(function(f){
   f.hidden=!(f.dataset.series===st.series&&f.dataset.role===st.role);});
  root.querySelectorAll('[data-set]').forEach(function(b){
   var kv=b.dataset.set.split('=');
   b.setAttribute('aria-pressed',String(st[kv[0]]===kv[1]));});
 }
 root.querySelectorAll('[data-set]').forEach(function(b){
  b.addEventListener('click',function(){var kv=b.dataset.set.split('=');
   st[kv[0]]=kv[1];draw();});});
 draw();
})();
</script>"""


def render(doc: dict) -> str:
    pr = projector(bbox(doc))
    blocks = doc["series_blocks"]
    # series를 **먼저** 고른다 — 하나의 스크러버에서 총선·대선을 섞지 않는다
    sers = "".join(
        f'<button type="button" data-set="series={esc(b["comparison_series_id"])}">'
        f'{esc(SERIES_LABEL.get(b["comparison_series_id"], b["comparison_series_id"]))}'
        f'</button>' for b in blocks)
    roles = "".join(
        f'<button type="button" data-set="role={esc(s["role"])}">'
        f'{esc(s["role_label"])}</button>' for s in blocks[0]["states"])
    # JS가 없어도 **정확히 한 프레임**은 보인다. 다 보이면 series를 섞어 보여주는 셈이다.
    frames = "".join(frame(s, pr, b["comparison_series_id"],
                           visible=(bi == 0 and si == 0))
                     for bi, b in enumerate(blocks)
                     for si, s in enumerate(b["states"]))
    leg = "".join(f'<span class="mt-key"><i style="background:{c}"></i>'
                  f'{FAM_LABEL[k]}</span>' for k, c in FAM_COLOR.items() if k != "other")
    leg += ('<span class="mt-key"><i style="background:#9aa3ad"></i>복수 계보'
            '(계열 hue 없음)</span>'
            '<span class="mt-key"><i style="background:#d7dbe0"></i>계보 미확인·무소속'
            '</span><span class="mt-key"><i style="background:#eceef1"></i>'
            '이 경계로 표시 불가</span>')
    # 명도로 무언가를 인코딩하면 키가 있어야 한다. currentColor로 두면 세 칸이
    # 전부 흐린 회색이라 단계가 안 보였다 — 실제 계열색 하나로 예시를 든다.
    leg += ('<br><span class="mt-key">1위 계열 득표 비율</span>' + "".join(
        f'<span class="mt-key"><i style="background:{FAM_COLOR["conservative"]};'
        f'opacity:{o}"></i>{lab}</span>' for _, _, lab, o in STEPS))
    d0 = blocks[0]
    return f"""<section class="mt" data-series="{esc(d0['comparison_series_id'])}"
 data-role="{esc(d0['states'][0]['role'])}">
<h2>{esc(doc['region'])} 지도 타임랩스</h2>
<p class="mt-lead">경계 · 선거 · 투영은 다른 층입니다. <b>결과가 있다고 해서 지금
경계에 칠할 수 있는 것은 아닙니다</b> — 칠할 수 없는 경계는 그리되 정치색을 주지
않습니다.</p>
<div class="mt-ctl"><label>비교 series</label><div class="mt-seg">{sers}</div></div>
<div class="mt-ctl"><label>시점</label><div class="mt-seg">{roles}</div></div>
{DEFS}{frames}
<p class="mt-legend">{leg}</p>
<p class="mt-note">선거 사이를 보간하지 않습니다. 각 시점은 그 이전 마지막 선거의
결과를 보여주며, 경계는 행정구역 사건일에 이산 전환합니다.</p>
</section>"""


def main(regions: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(SRC.glob("*.json")):
        if regions and f.stem not in regions:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if not d.get("series_blocks"):
            continue
        html = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{esc(d["region"])} 지도 타임랩스</title>{STYLE}</head>'
                f'<body>{render(d)}{SCRIPT}</body></html>')
        (OUT / f"{f.stem}.html").write_text(html, encoding="utf-8")
        n += 1
        print(f"  {d['region']}: series {len(d['series_blocks'])} · 프레임 "
              f"{sum(len(b['states']) for b in d['series_blocks'])}")
    print(f"\n→ {OUT.name}/ {n}개")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
