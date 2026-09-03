"""archive 페이지 구조 검증 — 재구성이 섹션·앵커를 잃지 않았는지.

정보 위계를 바꾸는 작업은 조용히 섹션을 떨어뜨리기 쉽다. 앵커가 사라지면 외부 링크와
검색엔진 진입이 깨지는데 화면만 보면 멀쩡해 보인다.

실행: python3 tests/test_archive_structure.py
"""
from __future__ import annotations
import pathlib
import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 지선 archive가 반드시 갖고 있어야 하는 앵커.
REQUIRED_LOCAL = [
    "ar-offices", "ar-governor-hex-section", "ar-metro-hex-section",
    "ar-council-hex-section", "ar-winners-section", "ar-exitpoll",
    "ar-polls-link", "ar-byelection", "ar-pledge-realm-section", "ar-compare-section",
]
fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}{'' if cond else ' — ' + str(detail)}")
    if not cond:
        fails.append(name)


def main():
    fp = ROOT / "archive/9th-local-2026/index.html"
    html = fp.read_text(encoding="utf-8")
    ids = set(re.findall(r'id="(ar-[a-z0-9-]+)"', html))
    missing = [i for i in REQUIRED_LOCAL if i not in ids]
    ck("지선 archive 필수 앵커 보존", not missing, missing)

    ck("태그 균형(section)", html.count("<section") == html.count("</section>"))
    ck("태그 균형(div)", html.count("<div") == html.count("</div>"))

    groups = re.findall(r'ar-group-title">([^<]*)', html)
    ck("서사 그룹 6개", len(groups) == 6, groups)
    ck("그룹 순서: 결과가 먼저", groups and groups[0] == "결과", groups[:1])
    ck("비교가 결과 다음", len(groups) > 1 and groups[1] == "무엇이 바뀌었나", groups[:2])

    # 회차 종류마다 최소 그룹 수 — 한 회차만 손대고 끝나는 실수를 잡는다.
    # 종류마다 있는 섹션이 다르므로 기대치도 다르다(총선은 비교·공약이 없다).
    MIN_GROUPS = {"local": 5, "pres": 3, "general": 2, "byelection": 2}
    def kind_of(name):
        if "byelection" in name:
            return "byelection"
        if "-pres-" in name:
            return "pres"
        if "-general-" in name:
            return "general"
        return "local"
    bad = []
    n_checked = 0
    for f in glob.glob(str(ROOT / "archive/*/index.html")):
        name = Path(f).parent.name
        h = Path(f).read_text(encoding="utf-8")
        n = len(re.findall(r'ar-group-title">', h))
        n_checked += 1
        if n < MIN_GROUPS[kind_of(name)]:
            bad.append(f"{name}({n})")
    ck(f"archive {n_checked}개 전부 종류별 최소 그룹 충족", not bad, bad[:6])

    # 빈 그룹을 만들지 않는다 — 그룹 안에 섹션이 최소 하나
    empty = []
    for f in glob.glob(str(ROOT / "archive/*/index.html")):
        h = Path(f).read_text(encoding="utf-8")
        for blk in re.findall(r'<div class="ar-group">([\s\S]*?)</div>', h):
            if '<section' not in blk:
                empty.append(Path(f).parent.name)
                break
    ck("빈 그룹 없음", not empty, empty[:5])

    # 결손을 0으로 쓰지 않는다 — 1~4회 지선은 원자료에 voters가 없다.
    # '투표율 0.0%'는 사용자가 실제 값으로 읽어서, 없던 사실이 만들어진다.
    zero = []
    for f in glob.glob(str(ROOT / "archive/*/index.html")):
        if "투표율 0.0%" in Path(f).read_text(encoding="utf-8"):
            zero.append(Path(f).parent.name)
    ck("투표율 0.0%로 찍힌 회차 없음", not zero, zero[:5])

    # ── 비례대표를 승자독식으로 세지 않는가 ────────────────────────────────
    # 막는 사고: 비례 의석을 '시도별 1위'로 세는 것. 2026-09까지 archive 총선 3쪽이
    # ("7","sido")에서 won을 세어 **비례 46석을 '17석'으로** 적고 있었다(17개 시도의
    # 1위 정당 하나씩). 이 저장소가 금기로 삼은 '비례를 승자독식으로 그리기'를
    # 표로 하고 있었던 셈이다(docs/absence.md·no-winner-take-all).
    #
    # 정본은 전국 행의 proportional_seats다. 시도별 비례 표는 아예 없어야 한다 —
    # 의석이 전국 단위로 배분되므로 '시도별 몇 석'이 존재하지 않는다.
    import json as _j
    import re as _re
    bad_prop, sido_prop = [], []
    for f in sorted(glob.glob(str(ROOT / "archive" / "*" / "index.html"))):
        eid = pathlib.Path(f).parent.name
        h = pathlib.Path(f).read_text(encoding="utf-8")
        if "ar-by-sido-7" in h:
            sido_prop.append(eid)
        m = _re.search(r"비례대표</td><td>(\d+)석", h)
        if not m:
            continue
        rp = ROOT / "data" / "results" / f"{eid}.json"
        if not rp.is_file():
            continue
        try:
            races = _j.loads(rp.read_text(encoding="utf-8")).get("races") or []
        except Exception:
            continue
        want = 0
        for r in races:
            if r.get("sg_typecode") == "7" and r.get("scope") == "nation":
                want = sum((c.get("proportional_seats") or c.get("seats") or 0)
                           for c in r.get("candidates") or [])
        if want and int(m.group(1)) != want:
            bad_prop.append(f"{eid}: 페이지 {m.group(1)}석 ≠ 배분 {want}석")
    ck("비례 의석이 전국 배분과 같다", not bad_prop, str(bad_prop[:3]))
    ck("비례를 시도별로 세는 표가 없다", not sido_prop,
       f"{len(sido_prop)}쪽 — {sido_prop[:3]}")

    # 스크립트 로드 순서 — trust는 렌더러보다 먼저 와야 mount가 동작한다
    it, ic = html.find("assets/trust.js"), html.find("assets/archive/core.js")
    ck("trust.js가 core.js보다 먼저 로드", it != -1 and it < ic)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
