"""수도권 손배치 v6 — 세로 구분 sharp, col 8 경기 only, 송파·강동 row 6."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO_DIR = ROOT / "data/geo"

# 서울 25 cell — col 3~7 row 2~6 (5×5 정확)
SEOUL = {
    '은평구': (3, 2), '종로구': (4, 2), '강북구': (5, 2), '도봉구': (6, 2), '노원구': (7, 2),
    '강서구': (3, 3), '서대문구': (4, 3), '성북구': (5, 3), '동대문구': (6, 3), '중랑구': (7, 3),
    '양천구': (3, 4), '마포구': (4, 4), '중구': (5, 4), '성동구': (6, 4), '광진구': (7, 4),
    '영등포구': (3, 5), '동작구': (4, 5), '용산구': (5, 5), '서초구': (6, 5), '강남구': (7, 5),
    '구로구': (3, 6), '금천구': (4, 6), '관악구': (5, 6), '송파구': (6, 6), '강동구': (7, 6),
}
# 인천 13 cell — col 0~2 row 0~4
INCHEON = {
    '강화군': (0, 0), '검단구': (1, 0), '계양구': (2, 0),
    '서구': (0, 1), '동구': (1, 1), '부평구': (2, 1),
    '중구': (0, 2), '제물포구': (1, 2), '남동구': (2, 2),
    '영종구': (0, 3), '남구': (1, 3), '미추홀구': (1, 3),
    '옹진군': (0, 4), '연수구': (1, 4),
}
# 경기 31 cell — col 3~8 외곽 + col 8 동측
GYEONGGI = {
    # row 0 col 3~8: 6 (북)
    '파주시': (3, 0), '양주시': (4, 0), '연천군': (5, 0),
    '동두천시': (6, 0), '포천시': (7, 0), '가평군': (8, 0),
    # row 1 col 3~8: 6 (서울 위)
    '김포시': (3, 1), '고양시': (4, 1), '의정부시': (5, 1),
    '남양주시': (6, 1), '구리시': (7, 1), '하남시': (8, 1),
    # col 8 row 2~5: 4 (동측)
    '양평군': (8, 2), '광주시': (8, 3), '여주시': (8, 4), '이천시': (8, 5),
    # col 8 row 6: 1
    '안성시': (8, 6),
    # row 7 col 3~8: 6 (서울 아래)
    '부천시': (3, 7), '광명시': (4, 7), '시흥시': (5, 7),
    '안산시': (6, 7), '과천시': (7, 7), '안양시': (8, 7),
    # row 8 col 3~8: 6
    '성남시': (3, 8), '용인시': (4, 8), '화성시': (5, 8),
    '의왕시': (6, 8), '군포시': (7, 8), '수원시': (8, 8),
    # row 9 col 5·6: 2 (남)
    '오산시': (5, 9), '평택시': (6, 9),
}

CAPITAL = {
    '서울특별시': SEOUL, '인천광역시': INCHEON, '경기도': GYEONGGI,
}


def apply(src_name: str, out_suffix: str = "_v2"):
    src = GEO_DIR / src_name
    cells = json.loads(src.read_text(encoding="utf-8"))
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
        c["c"], c["r"] = pos
        found[sido] += 1
    print(f"\n=== {src_name} ===")
    for sido in CAPITAL:
        print(f"  {sido}: {found[sido]} cell")
        if missing[sido]:
            print(f"    missing: {missing[sido][:3]}...")
    out = src.with_name(src.stem + out_suffix + src.suffix)
    out.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    for src in ["sigungu_hex.json", "sigungu_hex_legacy.json"]:
        apply(src)
