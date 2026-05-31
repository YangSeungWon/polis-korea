"""수도권 (서울·인천·경기) cell 위치 손배치 plan 적용 v2 — dense (빈자리 최소화).

격자: col 0~9, row 0~9 (대략). 한국 모양 일부 양보, 빈자리 ↓.

사용:
  python3 scripts/apply_capital_layout.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO_DIR = ROOT / "data/geo"

# 서울 25 cell (col 3~7, row 2~6) 5x5
SEOUL = {
    '은평구': (3, 2), '종로구': (4, 2), '강북구': (5, 2), '도봉구': (6, 2), '노원구': (7, 2),
    '강서구': (3, 3), '서대문구': (4, 3), '성북구': (5, 3), '동대문구': (6, 3), '중랑구': (7, 3),
    '양천구': (3, 4), '마포구': (4, 4), '중구': (5, 4), '성동구': (6, 4), '광진구': (7, 4),
    '영등포구': (3, 5), '동작구': (4, 5), '용산구': (5, 5), '서초구': (6, 5), '강남구': (7, 5),
    '구로구': (3, 6), '금천구': (4, 6), '관악구': (5, 6), '강동구': (8, 4), '송파구': (8, 5),
}
# 인천 13 cell (col 0~2, row 2~5) + col 0 row 6
INCHEON = {
    '강화군': (0, 1), '검단구': (1, 1),
    '서구': (0, 2), '계양구': (1, 2), '부평구': (2, 2),
    '영종구': (0, 3), '중구': (1, 3), '동구': (2, 3),
    '옹진군': (0, 4), '남구': (1, 4), '미추홀구': (1, 4), '남동구': (2, 4),
    '연수구': (0, 5), '제물포구': (1, 5),
}
# 경기 31 cell — 서울 사방 둘러쌈, dense
GYEONGGI = {
    # row 0 (북) 7 cell
    '파주시': (1, 0), '양주시': (2, 0), '연천군': (3, 0), '동두천시': (4, 0),
    '의정부시': (5, 0), '포천시': (6, 0), '가평군': (7, 0),
    # row 1 (북·동) 3 cell
    '김포시': (0, 0), '고양시': (2, 1), '남양주시': (6, 1),
    # row 2~3 동측 4 cell
    '구리시': (8, 2), '양평군': (9, 2),
    '하남시': (8, 3), '광주시': (9, 3),
    # row 4·5 동측 2 cell
    '여주시': (9, 5),
    # row 5·6 동남 1 cell
    '이천시': (9, 6),
    # row 6 서울 옆 (서·동) 3 cell
    '부천시': (2, 5), '과천시': (6, 6), '광명시': (2, 6),
    # row 7 (남) 5 cell
    '시흥시': (3, 7), '안산시': (4, 7), '안양시': (5, 7), '성남시': (6, 7), '용인시': (7, 7),
    # row 8 (남) 5 cell
    '화성시': (3, 8), '의왕시': (4, 8), '군포시': (5, 8), '수원시': (6, 8), '오산시': (7, 8),
    # row 9 (가장 남) 2 cell
    '안성시': (5, 9), '평택시': (6, 9),
}

CAPITAL = {
    '서울특별시': SEOUL,
    '인천광역시': INCHEON,
    '경기도': GYEONGGI,
}


def apply(src_name: str, out_suffix: str = "_v2"):
    src = GEO_DIR / src_name
    cells = json.loads(src.read_text(encoding="utf-8"))
    changed = 0
    found = {sido: 0 for sido in CAPITAL}
    missing = {sido: [] for sido in CAPITAL}
    for c in cells:
        sido = c.get("sido", "")
        name = c.get("name", "")
        layout = CAPITAL.get(sido)
        if not layout:
            continue
        pos = layout.get(name)
        if not pos:
            missing[sido].append(name)
            continue
        new_c, new_r = pos
        if c["c"] != new_c or c["r"] != new_r:
            changed += 1
        c["c"] = new_c
        c["r"] = new_r
        found[sido] += 1

    print(f"\n=== {src_name} ===")
    for sido in CAPITAL:
        print(f"  {sido}: {found[sido]} cell 적용")
        if missing[sido]:
            print(f"    missing: {missing[sido]}")

    out = src.with_name(src.stem + out_suffix + src.suffix)
    out.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out.name} ({changed} 변경)")


if __name__ == "__main__":
    for src in ["sigungu_hex.json", "sigungu_hex_legacy.json"]:
        apply(src)
