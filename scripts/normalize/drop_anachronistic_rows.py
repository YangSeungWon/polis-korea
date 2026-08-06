"""개칭 **이후** 이름으로 들어온 시대착오 행을 걷어낸다.

소스에 따라 행정구역 개칭을 **소급 적용**해 표기한다. 그래서 개칭 전 선거인데도
새 이름 행이 하나 더 들어오고, 같은 지역이 두 행이 된다. 실데이터는 그 시점 이름에
붙고 새 이름 행은 빈 껍데기로 남는다:

    7회(2018-06-13) 인천 남구 178,715표·2석   ← 그 시점 이름, 실데이터
    7회             인천 미추홀구  0표·0석    ← 개칭(2018-07-01) 후 이름, 유령

빈 행이 남으면 지도에서 '자료 없음' 칸이 되고 집계 수도 어긋난다.

**그 시점 이름을 지우지 않는다.** 지우는 것은 시대착오 쪽이다 — 1995년을 '이천시'로
칠하지 않는 것과 같은 규칙이다([[region_entity]]).

판정 근거는 `data/geography/events.json`의 rename 이벤트뿐이다. 이름이 비슷하다고
합치지 않는다.

사용: python scripts/normalize/drop_anachronistic_rows.py [--write]
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"
EVENTS = ROOT / "data/geography/events.json"


def renames() -> list:
    """(시도, 옛이름, 새이름, 시행일) — 영역이 그대로인 개명만."""
    out = []
    for e in json.loads(EVENTS.read_text(encoding="utf-8"))["events"]:
        if e.get("kind") != "admin_unit" or e.get("type") != "rename":
            continue
        if e.get("territorial_continuity") != "same":
            continue
        if len(e.get("from") or []) != 1 or len(e.get("to") or []) != 1:
            continue
        f, t = e["from"][0], e["to"][0]
        out.append((f["parent"], f["name"], t["name"], e["effective_date"], e["id"]))
    return out


def has_data(r: dict) -> bool:
    cs = r.get("candidates") or []
    return any((c.get("votes") or 0) or (c.get("seats") or 0) for c in cs)


def main(write: bool) -> int:
    rn = renames()
    if not rn:
        print("rename 이벤트 없음"); return 0
    total = 0
    for path in sorted(RESULTS.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        races = doc.get("races") or doc.get("district") or []
        if not isinstance(races, list):
            continue
        date = (doc.get("_meta") or {}).get("election_date") or ""
        if not date:
            continue
        drop = []
        for parent, old, new, eff, eid in rn:
            if date >= eff:
                continue                 # 개칭 후 선거 — 새 이름이 맞다
            # 그 시점 이름 행이 **실데이터를 갖고** 있을 때만 새 이름 행을 유령으로 본다
            for tc in {r.get("sg_typecode") for r in races}:
                same = [r for r in races if r.get("sg_typecode") == tc
                        and r.get("sido") == parent]
                real = [r for r in same if r.get("sigungu") == old and has_data(r)]
                ghost = [r for r in same if r.get("sigungu") == new and not has_data(r)]
                if real and ghost:
                    for g in ghost:
                        drop.append((g, f"{parent} {new}(개칭 {eff} 이전 선거) ← {eid}"))
        if not drop:
            continue
        for g, why in drop:
            print(f"  {path.name}: tc{g.get('sg_typecode')} {why}")
        total += len(drop)
        if write:
            ids = {id(g) for g, _ in drop}
            key = "races" if doc.get("races") else "district"
            doc[key] = [r for r in races if id(r) not in ids]
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print(f"\n시대착오 행 {total}건{'' if write else ' (--write 없이 실행 — 저장 안 함)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--write" in sys.argv))
