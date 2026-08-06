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



# --- 국정지지율 스파크라인 -----------------------------------------------------
# 능력 패널 6개에 전부 미니 차트를 넣었다가 5개를 걷어냈다. 라벨 없는 막대·구간은 읽히지
# 않는다 — 무엇의 크기인지 알 수 없으면 그냥 무늬다. 시계열만 남긴 이유는 모양 자체가
# 의미를 갖기 때문이다(오르내림과 정권별 궤적은 라벨 없이도 읽힌다).
#
# 5개 조사기관을 모두 합친다. 갤럽만 쓰면 272건이지만 리얼미터·NBS·한국리서치·일반
# 조사까지 1,600건 넘고, 기관별 house effect가 섞여 상쇄된다. 월별 중앙값으로 묶어
# 개별 조사의 튐을 죽이고 궤적만 남긴다.

W, H = 168, 44
APPROVAL_FILES = ("approval_gallup.json", "approval_realmeter.json", "approval_nbs.json",
                  "approval_hrc.json", "approval_general.json")


def approval_series() -> tuple[list, str]:
    """((월오프셋, 값) 리스트, 대통령 이름) — **현 정부 구간만**.

    홈은 '지금'을 보는 자리다. 2015년부터 11년치를 168px에 넣으면 궤적이 뭉개지고, 정권이
    네 번 바뀐 선이 무엇을 말하는지도 애매해진다. 현 정부만 잘라 내면 취임 이후 흐름이
    그대로 읽힌다. 역대 전체는 /tracker.html이 제대로 보여준다.

    x는 배열 인덱스가 아니라 실제 경과 월 — 조사가 없는 달이 있어 인덱스로 그리면
    그 구간이 압축돼 시간이 왜곡된다.
    """
    from collections import defaultdict
    from statistics import median
    by_month: dict[str, list] = defaultdict(list)
    subj: dict[str, str] = {}
    for name in APPROVAL_FILES:
        fp = ROOT / "data/polls" / name
        if not fp.exists():
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in d.get("records") or d.get("polls") or []:
            st, pos = (r.get("period_start") or ""), r.get("positive")
            if len(st) >= 7 and pos is not None:
                by_month[st[:7]].append(float(pos))
                subj.setdefault(st[:7], r.get("subject") or "")
    months = sorted(by_month)
    if not months:
        return [], ""
    who = subj.get(months[-1]) or ""
    cur = [m for m in months if subj.get(m) == who]
    # 취임 달은 전임과 조사가 섞이므로(2022-05처럼) 연속 구간의 시작부터 자른다.
    if len(cur) < 4:
        return [], ""
    y0, m0 = int(cur[0][:4]), int(cur[0][5:7])
    off = lambda m: (int(m[:4]) - y0) * 12 + (int(m[5:7]) - m0)
    return [(off(m), median(by_month[m])) for m in cur], who


def approval_spark() -> str:
    pts, _who = approval_series()
    if len(pts) < 4:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    span = pts[-1][0] or 1
    step = W / span
    xy = [(o * step, H - 4 - (v - lo) / rng * (H - 10)) for o, v in pts]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    area = f"0,{H} " + line + f" {W},{H}"
    return (f'<svg class="cap-viz" viewBox="0 0 {W} {H}" preserveAspectRatio="none" '
            f'role="img" aria-label="현 정부 국정지지율 — 5개 조사기관 월별 중앙값" '
            f'focusable="false">'
            f'<polygon points="{area}" fill="currentColor" opacity="0.13"/>'
            f'<polyline points="{line}" fill="none" stroke="currentColor" stroke-width="1.5" '
            f'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
            f'</svg>')


def row(href: str, title: str, sub: str, figure: str, viz: str = "") -> str:
    """능력 한 줄. 카드 대신 색인 행 — 수치가 한 열로 정렬돼 커버리지가 표처럼 읽힌다."""
    return (f'      <a class="cap-row" href="{href}">\n'
            f'        <span class="cap-name">{title}</span>\n'
            f'        <span class="cap-desc">{sub}</span>\n'
            f'        <span class="cap-viz-cell">{viz}</span>\n'
            f'        <span class="cap-fig">{figure}</span>\n'
            f'      </a>\n')


def approval_figure() -> str:
    pts, who = approval_series()
    if not pts:
        return "5개 조사기관 통합"
    return f"{who} 정부 {pts[-1][0] + 1}개월 · 5개 기관" if who else "5개 조사기관 통합"


def build(c: dict) -> str:
    """능력 목록 — 여론 / 사람 / 맥락.

    설명은 문장이 아니라 조각으로 쓴다 — 이 사이트의 다른 설명이 그렇다('17개 시·도',
    '1987~2036 · 27 역대 + 8 향후'). '~해 본다' 같은 종결로 설명하면 그 줄만 말이 많아진다.

    카드 그리드가 아니라 색인 행이다. 홈 위쪽은 이미 대시보드 패널(진행 중인 선거)이라,
    아래까지 같은 상자가 이어지면 스크롤이 평평해진다. 행으로 두면 수치가 오른쪽 한 열에
    정렬돼 '무엇을 얼마나 담고 있나'가 표처럼 읽히고, 위쪽 패널과 리듬이 갈린다.
    """
    f = lambda n: f"{n:,}"
    spark = approval_spark()
    out = [START + " — scripts/build/build_home_capabilities.py 자동 갱신. 손수정 X. -->"]
    out.append('  <section class="dash-section cap-sec">')
    out.append('    <h2 class="dash-section-title">더 볼 것</h2>')

    groups = [
        ("여론", [
            ("/tracker.html", "지지율 추이",
             "국정평가 · 정당지지 · 차기주자",
             approval_figure(), spark),
            ("/polls.html", "여론조사",
             "회차별 조사와 실제 결과 대조",
             f"NESDC 등록 {f(c['poll'])}건", ""),
        ]),
        ("사람", [
            ("/search.html", "출마 이력",
             "당선·낙선 전적 · 정당 변천",
             f"{f(c['person'])}명", ""),
        ]),
        ("맥락", [
            ("/parties.html", "정당사",
             "창당 · 합당 · 해산 계보",
             f"정당 {f(c['party'])}개", ""),
            ("/chronology.html", "근현대사 연표",
             "공화국 · 개헌 · 항쟁 · 선거",
             f"{c['republic']}개 공화국 · 주요 사건 {c['event']}건", ""),
        ]),
    ]
    if c["pledge"]:
        groups[1][1].append(
            ("/archive/9th-local-2026/", "선거공약",
             "공약서 원문 · 낙선자 포함",
             f"{f(c['pledge'])}건 · {f(c['pledge_people'])}명", ""))

    for label, rows in groups:
        out.append(f'    <div class="cap-group">')
        out.append(f'      <h3 class="cap-eyebrow">{label}</h3>')
        for href, title, sub, fig, viz in rows:
            out.append(row(href, title, sub, fig, viz).rstrip("\n"))
        out.append('    </div>')
    out.append('  </section>')
    # 데이터 제품에서 freshness는 장식이 아니다 — '지난 선거를 진행이라 하네'를 한 번
    # 겪으면 나머지 숫자도 의심받는다. 무엇이 언제 갱신됐는지 화면에 남긴다.
    fresh = data_freshness()
    if fresh:
        out.append(f'  <p class="cap-fresh">데이터 갱신 <time datetime="{fresh}">'
                   f'{fresh}</time> · 출처는 각 화면에 표기</p>')
    out.append("  " + END)
    return "\n".join(out)


def data_freshness() -> str:
    """화면이 실제로 쓰는 데이터의 최신 갱신일. **빌드 시각이 아니다** — 빌드는 매일
    돌아도 데이터가 안 바뀔 수 있고, 사용자가 알고 싶은 건 자료 쪽이다."""
    # 파일 **내용**의 타임스탬프만 쓴다. mtime이나 빌드 시각을 쓰면 같은 커밋에서
    # 두 번 돌릴 때 값이 달라져 생성기 멱등성 검사가 매번 깨진다.
    #
    # 결과 파일은 크다 — 통째로 파싱하지 않고 앞부분에서 `_meta`만 훑는다.
    newest = ""
    heads = [ROOT / "data/polls/aggregated.json", ROOT / "data/timeline.json"]
    heads += sorted((ROOT / "data/results").glob("*.json"))
    pat = re.compile(r'"(?:fetched_at|generated_at|updated|_updated)"\s*:\s*"(\d{4}-\d{2}-\d{2})')
    for f in heads:
        try:
            with f.open(encoding="utf-8") as fh:
                head = fh.read(4096)
        except OSError:
            continue
        for m in pat.finditer(head):
            newest = max(newest, m.group(1))
    return newest


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
