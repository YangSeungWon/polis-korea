"""assembly_member_map.json 재생성 — 국회 '정보 통합 API' xlsx 단일 소스, MONA코드 기준.

기존 parse_assembly_members.py는 여러 xlsx를 (이름+한자)로 병합해 동명+동한자 인물을
한 명으로 합치는 버그가 있었다(예: 김문수 金文洙 — 경기지사 1951년생 ↔ 순천 22대 1968년생).
통합 API는 의원마다 고유 MONA코드 + 생년월일 + 회차순 정당/선거구를 가져, 이걸로 빌드하면
동명이인이 원천 분리된다. openpyxl 없이 xlsx(zip+xml)를 직접 파싱.

소스: data/raw/assembly/데이터_국회의원 정보 통합 API.xlsx
  컬럼: [0]국회의원코드 [1]이름 [2]한자 [5]생일 [7]정당명(/구분) [8]선거구명(/구분) [13]당선대수(,구분)
출력: data/raw/assembly_member_map.json  ({"_meta":..., "persons":[{id,name,hanja,dob,careers:[{n,district,party}]}]})

사용: python3 scripts/build/build_assembly_map.py
"""
from __future__ import annotations
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
XLSX = ROOT / "data/raw/assembly/데이터_국회의원 정보 통합 API.xlsx"
OUT = ROOT / "data/raw/assembly_member_map.json"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _col(ref: str) -> int:
    s = "".join(c for c in ref if c.isalpha())
    n = 0
    for c in s:
        n = n * 26 + (ord(c) - 64)
    return n - 1


def _cell(c) -> str:
    is_ = c.find(NS + "is")
    if is_ is not None:
        return "".join(t.text or "" for t in is_.iter(NS + "t"))
    v = c.find(NS + "v")
    return v.text if v is not None else ""


def read_rows(xlsx: Path):
    z = zipfile.ZipFile(xlsx)
    root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for r in root.find(NS + "sheetData").findall(NS + "row"):
        d = {}
        for c in r.findall(NS + "c"):
            d[_col(c.get("r"))] = (_cell(c) or "").strip()
        rows.append(d)
    return rows


def parse_term(s: str):
    s = s.strip()
    if "제헌" in s:
        return 1
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def build_careers(terms_s: str, parties_s: str, districts_s: str):
    terms = [parse_term(t) for t in terms_s.split(",") if t.strip()]
    parties = [p.strip() for p in parties_s.split("/")] if parties_s else []
    districts = [d.strip() for d in districts_s.split("/")] if districts_s else []
    careers = []
    for i, n in enumerate(terms):
        if n is None:
            continue
        party = parties[i] if i < len(parties) else (parties[-1] if parties else "")
        dist = districts[i] if i < len(districts) else (districts[-1] if districts else "")
        careers.append({"n": n, "district": dist, "party": party})
    return careers


def main():
    rows = read_rows(XLSX)
    persons = []
    seen_ids = {}
    n_dup_id = 0
    for d in rows[1:]:
        mona = d.get(0, "")
        name = d.get(1, "")
        if not name:
            continue
        hanja = d.get(2, "")
        dob = d.get(5, "")
        careers = build_careers(d.get(13, ""), d.get(7, ""), d.get(8, ""))
        if not careers:
            continue
        pid = f"{name}_{dob}" if dob else f"{name}_{mona}"
        if pid in seen_ids:  # 동명+동생일(드뭄) → MONA로 유일화
            pid = f"{name}_{dob}_{mona}"
            n_dup_id += 1
        seen_ids[pid] = True
        persons.append({"id": pid, "mona": mona, "name": name,
                        "hanja": hanja, "dob": dob or None, "careers": careers})

    # 기존 map에만 있고 API에 없는 인물 보존(누락 방지)
    carried = 0
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            old_persons = old["persons"] if isinstance(old, dict) else old
            api_names = {p["name"] for p in persons}
            for p in old_persons:
                if p.get("name") not in api_names:
                    persons.append(p)
                    carried += 1
        except Exception:
            pass

    n_careers = sum(len(p["careers"]) for p in persons)
    out = {"_meta": {"source": "국회 정보통합 API xlsx (MONA코드 기준)",
                     "n_persons": len(persons), "n_careers": n_careers,
                     "carried_from_old": carried},
           "persons": persons}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}: {len(persons)}명 · {n_careers} careers "
          f"(API {len(persons)-carried} + 기존보존 {carried} · 동명동생일 {n_dup_id})")


if __name__ == "__main__":
    main()
