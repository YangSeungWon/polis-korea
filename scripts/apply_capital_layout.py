"""수도권 (서울·인천·경기) cell 위치 손배치 plan 적용.

plan: 사용자 의도 — 경기 서울 둘러쌈, 인천 서울 좌측 직접 연결,
경기 남부 두꺼움, 북부·동남부 얇음.

사용:
  python3 scripts/apply_capital_layout.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO_DIR = ROOT / "data/geo"

# 서울 25 cell (col 4~9, row 2~6)
SEOUL = {
    '은평구': (4, 2), '종로구': (5, 2), '강북구': (6, 2), '도봉구': (7, 2), '노원구': (8, 2),
    '강서구': (4, 3), '서대문구': (5, 3), '성북구': (6, 3), '동대문구': (7, 3), '중랑구': (8, 3),
    '양천구': (4, 4), '마포구': (5, 4), '중구': (6, 4), '성동구': (7, 4), '광진구': (8, 4), '강동구': (9, 4),
    '영등포구': (4, 5), '동작구': (5, 5), '용산구': (6, 5), '서초구': (7, 5), '강남구': (8, 5), '송파구': (9, 5),
    '구로구': (4, 6), '금천구': (5, 6), '관악구': (6, 6),
}
# 인천 13 cell (col 0~3, row 2~6) — 서울 좌측 직접 인접
INCHEON = {
    '강화군': (0, 2), '검단구': (2, 2),
    '서구': (1, 3), '계양구': (3, 3),
    '영종구': (0, 4), '중구': (1, 4), '부평구': (3, 4),
    '옹진군': (0, 5), '동구': (1, 5), '남구': (2, 5), '미추홀구': (2, 5), '남동구': (3, 5),
    '연수구': (1, 6), '제물포구': (2, 6),
}
# 경기 31 cell — 서울 사방 둘러쌈
GYEONGGI = {
    # row 0 (북 cluster)
    '파주시': (2, 0), '양주시': (3, 0), '연천군': (4, 0), '동두천시': (5, 0),
    '의정부시': (6, 0), '포천시': (7, 0), '가평군': (8, 0),
    # row 1 (서북·동북)
    '김포시': (1, 1), '고양시': (2, 1), '남양주시': (7, 1),
    # row 3·4·5 (동측)
    '구리시': (10, 3), '양평군': (11, 3),
    '하남시': (10, 4), '광주시': (11, 4),
    '여주시': (11, 5),
    # row 6 (서울 아래 간격)
    '부천시': (3, 6), '과천시': (7, 6), '이천시': (11, 6),
    # row 7 (서남·남)
    '광명시': (3, 7), '시흥시': (4, 7), '안산시': (5, 7),
    '안양시': (7, 7), '성남시': (8, 7),
    # row 8 (남 cluster)
    '화성시': (2, 8), '의왕시': (3, 8), '군포시': (4, 8), '수원시': (5, 8), '용인시': (6, 8),
    # row 9 (가장 남)
    '안성시': (3, 9), '평택시': (4, 9), '오산시': (5, 9),
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
        defined = len(set(CAPITAL[sido].values()))  # 좌표 unique
        print(f"  {sido}: {found[sido]} cell 적용, plan 정의 {len(CAPITAL[sido])}개 (좌표 {defined})")
        if missing[sido]:
            print(f"    missing: {missing[sido]}")

    out = src.with_name(src.stem + out_suffix + src.suffix)
    out.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out.name} ({changed} 변경)")


if __name__ == "__main__":
    for src in ["sigungu_hex.json", "sigungu_hex_legacy.json"]:
        apply(src)
