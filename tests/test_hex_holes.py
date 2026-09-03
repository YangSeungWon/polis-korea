"""hex 카토그램에 갇힌 빈칸이 없는가 — 그리고 시도가 더 쪼개지지 않았는가.

**"내부 빈칸 0"은 오래 주석에만 있었고 사실이 아니었다.** `build_zone_hex.py` 독스트링이
그렇게 선언해 뒀지만, 영남 70셀을 그 구조(대구 3×3 · 울산 3×2 L · 경북 wrap ·
경남/부산 bot)로 놓으면 빈칸 0인 후보가 탐색 공간에 아예 없다 — 최소가 2다. 그중
하나가 바깥으로 못 나가고 sigungu_hex (12,10)에 갇혔고(이웃: 대구 동구·울산 북구·
경북 영천시·청송군), 회차별 지선 hex는 5~9회에 같은 이유로 구멍이 있었다.
지도를 보면 대구와 경북 사이가 뚫려 보인다.

메우는 건 `fill_district_hex_holes.py`(slide-fill)다. 그런데 그건 생성기와 **다른**
스크립트라, build_zone_hex나 build_local_period_hex를 다시 돌리고 fill을 잊으면
구멍이 조용히 돌아온다. 파일이 커밋돼 있어 diff에도 안 걸린다. 그래서 여기서 잡는다.

시도 연결성도 함께 본다. 절대 기준이 아니라 **회귀 기준**이다 — district_hex_4·5·16은
centroid 비닝 결과 이미 시도가 끊겨 있고(그건 이 검사의 대상이 아니다), 새로 끊기는
것만 막는다. 실제로 첫 slide-fill이 포항시를 (13,10)→(12,10)으로 밀어 (13,11) 경북
셀을 고립시켰다. 구멍은 사라졌고 검사도 없었으니, 이게 없었으면 그대로 나갔다.

실행: .venv/bin/python tests/test_hex_holes.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
from fill_district_hex_holes import _holes, _split_groups  # noqa: E402

# 이미 시도가 끊겨 있는 레이아웃 — 고치는 건 별건이고, 여기선 **악화만** 막는다.
KNOWN_SPLIT = {
    "district_hex_16": {"경상북도"},
    "district_hex_4": {"강원특별자치도", "경기도", "경상북도", "전라남도",
                       "전북특별자치도", "충청남도", "충청북도"},
    "district_hex_5": {"강원특별자치도", "경기도", "경상남도", "경상북도", "전라남도",
                       "전북특별자치도", "충청남도", "충청북도"},
}


def layouts():
    """(이름, 셀배열). sigungu_hex_local.json은 회차 키 dict라 펼친다."""
    for p in sorted((ROOT / "data/geo").glob("*hex*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for key, cells in (doc.items() if isinstance(doc, dict) else [("", doc)]):
            if isinstance(cells, list) and cells and isinstance(cells[0], dict) and "c" in cells[0]:
                yield f"{p.stem}{':' + key if key else ''}", cells


def main() -> int:
    fails = []

    def ck(label, ok, detail=""):
        print(f"  {'✓' if ok else '✗'} {label}" + (f" — {detail}" if not ok and detail else ""))
        if not ok:
            fails.append(label)

    seen = 0
    holed, worsened = [], []
    print("[hex] 갇힌 빈칸 · 시도 연결성")
    for name, cells in layouts():
        seen += 1
        occ = {(c["c"], c["r"]): c for c in cells}
        holes, _ = _holes(occ)
        if holes:
            holed.append(f"{name}: {len(holes)}개 {holes[:3]}")
        if all("sido" in c for c in cells):
            base = KNOWN_SPLIT.get(name.split(":")[0], set())
            extra = set(_split_groups(occ, "sido")) - base
            if extra:
                worsened.append(f"{name}: {sorted(extra)}")

    ck(f"레이아웃을 실제로 읽었다 ({seen}개)", seen >= 25, str(seen))
    ck("갇힌 빈칸이 없다", not holed, "; ".join(holed[:4]))
    ck("시도가 새로 쪼개지지 않았다", not worsened, "; ".join(worsened[:4]))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
