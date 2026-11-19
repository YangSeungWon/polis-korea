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
# 최근 여론을 무엇으로 볼까 — 가장 최근 조사일에서 WINDOW_DAYS 안, **기관마다 가장 최근
# 조사 하나**. 날짜순으로 N건을 자르면 매주 내는 기관이 여러 번 들어가 그쪽으로 기운다.
# 하나만 쓰면(예전 정당 지지도) 그 주에 마지막으로 낸 기관이 헤드라인이 된다 — 같은
# 2주 사이 국민의힘이 기관에 따라 25%~48%로 갈렸다(조사 방식 차이, house effect).
# 그래서 중앙값과 **범위**를 함께 낸다. 범위를 지우면 기관 차이가 숨는다.
WINDOW_DAYS = 21
MIN_AGENCIES = 3   # 이보다 적은 기관이 다룬 정당은 요약에 올리지 않는다
# 트래커 차트(assets/tracker.js CANON·cleanCands)와 같은 정당명 정리.
CANON = {"민주당": "더불어민주당", "국힘": "국민의힘", "국민의 힘": "국민의힘"}
NON_PARTY = {"무소속", "없음", "기타", "무당층", "지지정당없음", "기타정당", "지지정당 없음"}


def esc(s) -> str:
    return (str(s if s is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _days(a: str, b: str) -> int:
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def latest_per_agency(rows: list) -> list:
    """가장 최근 조사일에서 WINDOW_DAYS 안의 조사 중 기관마다 가장 최근 하나."""
    if not rows:
        return []
    last = max(r["period_end"] for r in rows)
    best: dict = {}
    for r in rows:
        a = (r.get("agency") or "").strip()
        if not a or _days(r["period_end"], last) > WINDOW_DAYS:
            continue
        if a not in best or r["period_end"] > best[a]["period_end"]:
            best[a] = r
    return sorted(best.values(), key=lambda r: r["agency"])


def _stat(vals: list) -> dict:
    import statistics
    return {"mid": round(statistics.median(vals), 1), "lo": min(vals), "hi": max(vals), "n": len(vals)}


def approval() -> dict | None:
    """국정수행 평가 — 기관별 최근 조사의 중앙값과 범위."""
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
    recent = latest_per_agency(rows)
    if not recent:
        return None
    neg = [r["negative"] for r in recent if r.get("negative") is not None]
    last = max(recent, key=lambda r: r["period_end"])
    return {
        "subject": last.get("subject") or "",
        "positive": _stat([r["positive"] for r in recent]),
        "negative": _stat(neg) if neg else None,
        "from": min(r["period_end"] for r in recent),
        "as_of": last["period_end"],
        "agencies": [r["agency"] for r in recent],
    }


def clean_cands(poll: dict) -> dict:
    """한 조사 → {정당(정리된 이름): %}. tracker.js cleanCands와 같은 규칙 —
    '더불어민주당'이 따로 있는 조사의 '민주당'은 군소 오표기라 버린다."""
    cs = [c for c in (poll.get("candidates") or [])
          if c.get("pct") is not None and (c.get("party") or c.get("name"))]
    names = [(c.get("party") or c.get("name")).strip() for c in cs]
    has_dlp = "더불어민주당" in names
    out: dict = {}
    for c, n in zip(cs, names):
        if n == "민주당" and has_dlp:
            continue
        n = CANON.get(n, n)
        if n in NON_PARTY:
            continue
        out.setdefault(n, c["pct"])
    return out


def party() -> dict | None:
    """정당 지지도 — 기관별 최근 조사에서 정당마다 중앙값과 범위.

    조사마다 정당 항목이 달라 평균하면 없는 정당이 생긴다 — 그래서 정당마다 **그 정당을
    물은 조사만** 세고, MIN_AGENCIES 미만이 물은 정당은 올리지 않는다."""
    rows = []
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
            rows.append(p)
    recent = latest_per_agency(rows)
    if len(recent) < MIN_AGENCIES:
        return None
    by: dict = {}
    for p in recent:
        for n, v in clean_cands(p).items():
            by.setdefault(n, []).append(v)
    stats = sorted(((n, _stat(v)) for n, v in by.items() if len(v) >= MIN_AGENCIES),
                   key=lambda kv: -kv[1]["mid"])[:4]
    return {"from": min(p["period_end"] for p in recent), "as_of": max(p["period_end"] for p in recent),
            "n": len(recent), "parties": stats}


def _rng(st: dict) -> str:
    return f'{st["lo"]:g}~{st["hi"]:g}'


def block() -> str:
    ap, pt = approval(), party()
    rows = []
    if ap:
        who = f"{esc(ap['subject'])} " if ap["subject"] else ""
        pos, neg = ap["positive"], ap["negative"]
        rows.append(
            f'<div class="tk-sum-item"><div class="tk-sum-label">{who}국정수행 긍정</div>'
            f'<div class="tk-sum-value">{pos["mid"]}%</div>'
            # **산출방식이 값과 같은 자리에 있어야 한다.** 숫자만 떼어 보면(스니펫·공유)
            # 'polis의 자체 집계' 또는 '최신 단일 조사'로 읽힌다.
            f'<div class="tk-sum-sub">기관별 {_rng(pos)}%'
            + (f' · 부정 {neg["mid"]}%' if neg else '') + '</div>'
            f'<div class="tk-sum-sub">{len(ap["agencies"])}개 기관의 최근 조사 중앙값 '
            f'({esc(ap["from"])}~{esc(ap["as_of"])})<br>{esc(", ".join(ap["agencies"]))}</div></div>')
    if pt and pt["parties"]:
        (n0, s0), rest = pt["parties"][0], pt["parties"][1:]
        others = " · ".join(f'{esc(n)} {st["mid"]}% <span class="tk-sum-rng">({_rng(st)})</span>' for n, st in rest)
        rows.append(
            f'<div class="tk-sum-item"><div class="tk-sum-label">정당 지지도</div>'
            f'<div class="tk-sum-value">{esc(n0)} {s0["mid"]}%</div>'
            f'<div class="tk-sum-sub">기관별 {_rng(s0)}%</div>'
            f'<div class="tk-sum-sub">{others}</div>'
            f'<div class="tk-sum-sub">{pt["n"]}개 기관의 최근 조사 중앙값 ({esc(pt["from"])}~{esc(pt["as_of"])})</div></div>')
    if not rows:
        return START + " — 표시할 최근 조사가 없다 -->\n" + END
    out = [START + " — scripts/build/build_tracker_static.py 자동 갱신. 손수정 X. -->",
           '  <section class="tk-summary" aria-label="현재 지표 요약">',
           '    <div class="tk-sum-grid">']
    out += ["    " + r for r in rows]
    out += ['    </div>',
            '    <p class="tk-sum-meta">같은 시기에도 조사 방식(자동응답·전화면접 등)에 따라 '
            '기관마다 값이 크게 다릅니다. 괄호 안이 기관별 범위입니다. 보정이나 가중치는 '
            '적용하지 않았습니다.</p>',
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
