"""후보 ↔ 인물 링크 감사 — data/person-links/*.json.

잘못 연결된 인물 페이지는 없는 링크보다 나쁘다(다른 사람 이력을 그 사람 것으로 보여준다).
그래서 '링크가 많은가'보다 '링크가 가리키는 곳이 실제로 있는가'와 '모호한 건 안 이었는가'를
검사한다.

실행: python3 tests/test_person_links.py
"""
from __future__ import annotations
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}{'' if cond else ' — ' + str(detail)}")
    if not cond:
        fails.append(name)


def main():
    files = sorted(glob.glob(str(ROOT / "data/person-links/*.json")))
    if not files:
        print("링크 파일 없음 — skip")
        return 0
    total_links = dead = 0
    for f in files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for slug in d["links"].values():
            total_links += 1
            if not (ROOT / "person" / slug / "index.html").exists():
                dead += 1
    ck("모든 링크가 실제 인물 페이지를 가리킨다", dead == 0, f"죽은 링크 {dead}/{total_links}")

    # 동명이인은 연결하지 않는다 — unresolved에 남고 links에는 없어야 한다
    bad_amb = 0
    for f in files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for u in d.get("unresolved") or []:
            if u["key"] in d["links"]:
                bad_amb += 1
    ck("동명이인 키는 연결하지 않는다", bad_amb == 0, bad_amb)

    # 최신 회차는 커버리지가 높아야 한다 — 인물 페이지 생성 규칙이 깨지면 여기서 잡힌다
    cur = ROOT / "data/person-links/9th-local-2026.json"
    if cur.exists():
        m = json.loads(cur.read_text(encoding="utf-8"))["_meta"]
        rate = m["n_links"] / m["n_keys"] * 100 if m["n_keys"] else 0
        ck(f"9회 지선 링크율 90% 이상 (현재 {rate:.1f}%)", rate >= 90, f"{m['n_links']}/{m['n_keys']}")

    print(f"\n총 링크 {total_links:,} · {'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
