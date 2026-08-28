"""세 레인 재생의 프레임 목록이 성립하는가 (data/election_timelapse.json).

**막는 사고: 조용히 건너뛰기.** 지역별 결과가 없는 회차를 목록에서 빼면 그 시기에
선거가 없었던 것처럼 보인다 — 유신 시기 대선 6회가 통째로 사라진다. 없는 것은
'없다'고 적힌 자리로 남아야 한다(docs/absence.md).

그리고 프레임이 가리키는 그림이 실재해야 한다. 캡처를 다시 돌리며 키가 바뀌면
목록만 남고 그림이 404가 된다.

실행: .venv/bin/python tests/test_timelapse.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "election_timelapse.json"
fails: list[str] = []


def bad(m: str) -> None:
    fails.append(m)
    print(f"  ✗ {m}")


def main() -> int:
    print("세 레인 재생 프레임")
    if not SRC.is_file():
        bad("election_timelapse.json이 없다")
        return 1
    d = json.loads(SRC.read_text(encoding="utf-8"))
    lanes = d.get("lanes") or []
    if len(lanes) != 3:
        bad(f"레인이 3개가 아니다 — {len(lanes)}")

    # 매니페스트의 회차 수와 맞는가 — 빠뜨린 회차가 있으면 여기서 걸린다.
    mf = json.loads((ROOT / "data/map_manifest.json").read_text(encoding="utf-8"))["elections"]
    ai = {e["slug"] for e in json.loads(
        (ROOT / "data/archive_index.json").read_text(encoding="utf-8"))}
    n_frames = 0
    for L in lanes:
        kind = L.get("kind")
        want = {s for s, e in mf.items() if e.get("kind") == kind and s in ai}
        got = {f["slug"] for f in (L.get("frames") or [])}
        miss = sorted(want - got)
        if miss:
            bad(f"{L.get('name')}: {len(miss)}회차가 목록에서 빠졌다 — {miss[:3]}")
        if not L.get("means"):
            bad(f"{L.get('name')}: 그림이 무엇을 뜻하는지 안 적혀 있다")
        prev = ""
        for f in L.get("frames") or []:
            n_frames += 1
            if f["date"] < prev:
                bad(f"{L.get('name')}: 날짜 순서가 아니다 — {f['slug']}")
            prev = f["date"]
            if f.get("img"):
                p = ROOT / f["img"].lstrip("/")
                if not p.is_file():
                    bad(f"{f['slug']}: 그림이 없다 — {f['img']}")
            elif not f.get("note"):
                # 그림이 없으면 **왜 없는지** 적혀 있어야 한다. 안 적으면 화면이
                # 빈 칸을 아무 말 없이 보여주고, 읽는 사람은 자료 누락으로 읽는다.
                bad(f"{f['slug']}: 그림도 없고 이유도 없다")
    print(f"  레인 {len(lanes)} · 프레임 {n_frames} · "
          f"{d.get('years', ['?', '?'])[0]}~{d.get('years', ['?', '?'])[-1]}")

    # 간선을 지우지 않았는가 — 유신 시기 대선이 목록에 있어야 한다.
    pres = next((L for L in lanes if L.get("kind") == "presidential"), None)
    if pres:
        yushin = [f for f in pres["frames"] if "1972" <= f["date"][:4] <= "1981"]
        if len(yushin) < 4:
            bad(f"유신 시기 대선이 {len(yushin)}회만 있다 — 간선을 건너뛰면 "
                "그 시기에 선거가 없었던 것처럼 보인다")
        alt = [f for f in yushin if f.get("note")]
        if len(alt) != len(yushin):
            bad("간선 회차에 '간선'이라는 표시가 없다 — 다른 그림인데 지도처럼 보인다")

    if fails:
        print(f"\n실패 {len(fails)}건")
        return 1
    print("통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
