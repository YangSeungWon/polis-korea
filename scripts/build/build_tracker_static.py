"""지지율 페이지의 **정적 요약** — JS 없이도 페이지가 완성되게.

tracker.html은 '대통령 지지율'·'정당 지지율' 같은 직접 검색어를 받는 자리인데,
JS를 돌리지 않으면 설명 문구만 있고 **숫자가 하나도 없었다**. 검색엔진이 보는 것도,
느린 회선에서 처음 보는 것도 그 상태다.

그래서 차트가 그려지기 전에 읽을 수 있는 요약을 HTML에 박는다. 차트는 그걸
대체하는 게 아니라 위에 얹힌다(progressive enhancement) — 요약은 JS가 떠도 남는다.

## 숫자를 손으로 적지 않는다

값은 tracker.js가 읽는 **같은 파일**에서 뽑는다. 손으로 적으면 반드시 어긋난다.
그리고 기준일은 빌드일이 아니라 **조사 기간의 끝**이다 — 사용자가 알고 싶은 건
'언제 빌드했나'가 아니라 '언제까지의 여론인가'다.

없으면 만들지 않는다. 최근 조사가 없으면 그 줄은 빠진다.

사용: python scripts/build/build_tracker_static.py
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "tracker.html"
START = "<!-- TK_STATIC_START"
END = "<!-- TK_STATIC_END -->"
# 최근 몇 건을 평균할지 — 한 기관 한 조사만 쓰면 house effect가 그대로 헤드라인이 된다.
RECENT_N = 5


def esc(s) -> str:
    return (str(s if s is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def approval() -> dict | None:
    """국정수행 평가 — 최근 조사 평균. 기관마다 값이 달라 하나만 쓰면 편향이 실린다."""
    rows = []
    for f in sorted(glob.glob(str(ROOT / "data/polls/approval_*.json"))):
        if "scancache" in f:
            continue
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for r in d.get("records") or []:
            if r.get("positive") is None or not r.get("period_end"):
                continue
            rows.append(r)
    if not rows:
        return None
    rows.sort(key=lambda r: r["period_end"])
    recent = rows[-RECENT_N:]
    pos = [r["positive"] for r in recent if r.get("positive") is not None]
    neg = [r["negative"] for r in recent if r.get("negative") is not None]
    return {
        "subject": recent[-1].get("subject") or "",
        "positive": round(sum(pos) / len(pos), 1) if pos else None,
        "negative": round(sum(neg) / len(neg), 1) if neg else None,
        "as_of": recent[-1]["period_end"],
        "n": len(recent),
        "agencies": sorted({r.get("agency", "") for r in recent if r.get("agency")}),
    }


def party() -> dict | None:
    """정당 지지도 — 전국 단위 가장 최근 조사 하나. 정당은 조사마다 항목이 달라
    평균을 내면 없는 정당이 생긴다. 여기서는 한 조사를 그대로 인용하고 출처를 밝힌다."""
    best = None
    for f in sorted(glob.glob(str(ROOT / "data/polls/aggregated*.json"))):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for p in d.get("polls") or []:
            if p.get("metric_type") != "정당지지" or p.get("sido"):
                continue
            if not p.get("candidates") or not p.get("period_end"):
                continue
            if best is None or p["period_end"] > best["period_end"]:
                best = p
    if not best:
        return None
    cs = sorted((c for c in best["candidates"] if c.get("pct") is not None),
                key=lambda c: -c["pct"])[:4]
    return {"as_of": best["period_end"], "agency": best.get("agency", ""),
            "parties": [(c.get("name") or c.get("party"), c["pct"]) for c in cs]}


def block() -> str:
    ap, pt = approval(), party()
    rows = []
    if ap and ap["positive"] is not None:
        who = f"{esc(ap['subject'])} " if ap["subject"] else ""
        rows.append(
            f'<div class="tk-sum-item"><div class="tk-sum-label">{who}국정수행 긍정</div>'
            f'<div class="tk-sum-value">{ap["positive"]}%</div>'
            f'<div class="tk-sum-sub">부정 {ap["negative"]}% · 최근 {ap["n"]}개 조사 평균 '
            f'· {esc(", ".join(ap["agencies"][:3]))}</div></div>')
    if pt and pt["parties"]:
        # 헤드라인이 1위를 이미 말했다 — 아래 줄에서 또 쓰면 같은 값이 두 번 나온다
        top = " · ".join(f"{esc(n)} {v}%" for n, v in pt["parties"][1:])
        rows.append(
            f'<div class="tk-sum-item"><div class="tk-sum-label">정당 지지도</div>'
            f'<div class="tk-sum-value">{esc(pt["parties"][0][0])} {pt["parties"][0][1]}%</div>'
            f'<div class="tk-sum-sub">{top} · {esc(pt["agency"])}</div></div>')
    if not rows:
        return START + " — 표시할 최근 조사가 없다 -->\n" + END
    as_of = max([x["as_of"] for x in (ap, pt) if x] or [""])
    out = [START + " — scripts/build/build_tracker_static.py 자동 갱신. 손수정 X. -->",
           '  <section class="tk-summary" aria-label="현재 지표 요약">',
           '    <div class="tk-sum-grid">']
    out += ["    " + r for r in rows]
    out += ['    </div>',
            f'    <p class="tk-sum-meta">조사 기간 기준 {esc(as_of)}까지 · '
            '값은 개별 조사이며 기관마다 차이가 있습니다(house effect). '
            '아래 그래프에서 기관별 산포와 추세를 봅니다.</p>',
            '  </section>',
            "  " + END]
    return "\n".join(out)


def main() -> int:
    html = PAGE.read_text(encoding="utf-8")
    blk = block()
    if START in html:
        new = re.sub(re.escape(START) + r"[\s\S]*?" + re.escape(END), blk, html, count=1)
    else:
        anchor = '  <div id="tk-loading">'
        if anchor not in html:
            print("ERR: tracker.html에 삽입 지점이 없다", file=sys.stderr)
            return 1
        new = html.replace(anchor, blk + "\n\n" + anchor, 1)
    if new != html:
        PAGE.write_text(new, encoding="utf-8")
        print("→ tracker.html 정적 요약 갱신", file=sys.stderr)
    else:
        print("→ 변경 없음", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
