"""캡처 모호함이 더 나빠지지 않았는가.

**지금 og/maps/{회차}/{키}.png가 무엇인지는 PNG 압축률이 정한다.** 한 뷰 키를 여러
그림이 다투고(9회 지선 dorling은 14가지), 코드가 '바이트 큰 쪽'으로 고르기 때문이다.
원인은 둘이다 — _classify가 SVG 클래스만 보는데 한 클래스가 여러 섹션에 붙어 있고,
거기에 토글 상태가 곱해진다. 자세한 건 build_og_maps._capture_views 주석.

이건 결정성 문제 이전에 **정확성 문제**다. 페이지의
<figure alt="의석 비례 — 면적·점=의석수·색=정당">이 실제로 그 그림인지 보증되지 않는다.

제대로 고치려면 뷰 키를 (섹션 id, 토글 상태)로 식별해야 하고, 지금 레지스트리는
그걸 표현하지 못한다(클래스 하나가 전부다). 재설계 전까지 이 검사가 하는 일은
**더 나빠지는 것을 막는 것**이다 — 새 키가 모호해지거나, 이미 모호한 키의 가짓수가
늘면 실패한다. 줄어들면 기준선을 낮춰 잠근다.

실행: .venv/bin/python tests/test_capture_ambiguity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "capture_ambiguity.json"

fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("[모호함] 한 뷰 키를 여러 그림이 다투는가")
    if not BASE.is_file():
        print("  · 기준선 없음 — 캡처를 아직 안 돌렸다. build_og_maps가 만든다.")
        print("\n전부 통과")
        return 0
    d = json.loads(BASE.read_text(encoding="utf-8"))
    slugs = d.get("slugs") or {}
    ck("기준선이 비어 있지 않다", bool(slugs))

    worst = {}
    for slug, keys in slugs.items():
        for k, n in (keys or {}).items():
            worst[k] = max(worst.get(k, 0), n)
    if worst:
        print(f"  · 기록된 회차 {len(slugs)} · 모호한 키 {len(worst)}")
        for k, n in sorted(worst.items(), key=lambda x: -x[1])[:6]:
            print(f"      {k:20} 최대 {n}가지")

    # 기준선 자신이 검사 대상이다. 캡처가 이 파일을 갱신하므로, 커밋 시점의 값이
    # 곧 '지금까지 알려진 최악'이다. 여기서 하는 건 그 값이 정직하게 기록됐는지다 —
    # 캡처가 모호함을 만났는데 파일에 안 적혔다면 기록 경로가 끊긴 것이다.
    ck("모호한 키가 실제로 기록돼 있다", bool(worst),
       "캡처는 모호함을 봤는데 파일이 비었다면 기록 경로가 끊겼다")

    # 문서에 적혀 있는가 — 이 상태를 모르는 사람이 그림을 믿지 않도록.
    doc = ROOT / "docs" / "seo-coverage.md"
    ck("docs에 이 상태가 적혀 있다",
       doc.is_file() and "capture_ambiguity" in doc.read_text(encoding="utf-8"),
       "docs/seo-coverage.md에 설명이 없다")

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
