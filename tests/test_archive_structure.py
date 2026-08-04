"""archive 페이지 구조 검증 — 재구성이 섹션·앵커를 잃지 않았는지.

정보 위계를 바꾸는 작업은 조용히 섹션을 떨어뜨리기 쉽다. 앵커가 사라지면 외부 링크와
검색엔진 진입이 깨지는데 화면만 보면 멀쩡해 보인다.

실행: python3 tests/test_archive_structure.py
"""
from __future__ import annotations
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

    # 모든 지선 archive가 같은 구조여야 한다(한 회차만 손대고 끝나는 실수 방지)
    local = [f for f in glob.glob(str(ROOT / "archive/*-local-*/index.html"))]
    bad = []
    for f in local:
        h = Path(f).read_text(encoding="utf-8")
        if len(re.findall(r'ar-group-title">', h)) < 5:
            bad.append(Path(f).parent.name)
    ck(f"지선 archive {len(local)}개 모두 그룹 구조", not bad, bad)

    # 스크립트 로드 순서 — trust는 렌더러보다 먼저 와야 mount가 동작한다
    it, ic = html.find("assets/trust.js"), html.find("assets/archive/core.js")
    ck("trust.js가 core.js보다 먼저 로드", it != -1 and it < ic)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
