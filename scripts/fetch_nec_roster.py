"""9회 지선 등록 후보자 명부 fetch — NEC CndaSrchService.

CndaSrchService는 list endpoint 없고 name parameter 필수. polls에 등장한 후보들의 이름을
NEC API에 name으로 조회 → sgId=20260603 + sgTypecode (3/4/11) 매칭만 저장.

저장: data/raw/nec_roster_9th.json = {(sido, name): {sgg, jd, sg_typecode}}
산점도·hex의 "최종 등록 후보" 식별에 사용.

사용:
  NEC_API_KEY=... .venv/bin/python scripts/fetch_nec_roster.py
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGG = ROOT / "data" / "polls" / "aggregated.json"
OUT = ROOT / "data" / "raw" / "nec_roster_9th.json"
API = "https://apis.data.go.kr/9760000/CndaSrchService/getCndaSrchInqire"
SG_ID = "20260603"

# sgTypecode → office_level
TYPECODE_OFFICE = {"3": "광역단체장", "4": "기초단체장", "11": "교육감"}


def fetch_name(key: str, name: str) -> list[dict]:
    url = f"{API}?serviceKey={key}&name={urllib.parse.quote(name)}&pageNo=1&numOfRows=100"
    try:
        xml = urllib.request.urlopen(url, timeout=30).read()
    except Exception as e:
        print(f"  ! {name}: {e}", file=sys.stderr)
        return []
    root = ET.fromstring(xml)
    if root.findtext("header/resultCode") != "INFO-00":
        return []
    out = []
    for it in root.findall("body/items/item"):
        out.append({
            "sd": it.findtext("sdName") or "",
            "sgg": it.findtext("sggName") or "",
            "jd": it.findtext("jdName") or "",
            "sg_id": it.findtext("sgId") or "",
            "sg_typecode": it.findtext("sgTypecode") or "",
        })
    return out


def main():
    key = os.environ.get("NEC_API_KEY")
    if not key:
        print("환경변수 NEC_API_KEY 필요", file=sys.stderr)
        sys.exit(1)
    if not AGG.exists():
        print("aggregated.json 없음 — build_polls 먼저", file=sys.stderr)
        sys.exit(1)
    data = json.load(open(AGG, encoding="utf-8"))
    # polls의 candidates 중 (sido, name) 유니크 모음 (정상 한글 인명만)
    import re
    targets = set()
    for p in data["polls"]:
        sd = p.get("sido", "")
        for c in p.get("candidates", []):
            nm = (c.get("name") or "").strip()
            if not nm or not re.fullmatch(r"[가-힣]{2,4}", nm):
                continue
            targets.add((sd, nm))
    print(f"조회 대상 (sido, name) 유니크: {len(targets)}", file=sys.stderr)

    # 기존 cache 로드 (증분)
    existing = {}
    if OUT.exists():
        try:
            existing = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            existing = {}

    roster: dict[str, dict] = dict(existing)
    n_new = n_match = 0
    for i, (sd, nm) in enumerate(sorted(targets), 1):
        key_str = f"{sd}|{nm}"
        if key_str in roster:
            continue
        rows = fetch_name(key, nm)
        n_new += 1
        # sgId=20260603 + sd 매칭 + sgTypecode in 3/4/11
        match = None
        for r in rows:
            if r["sg_id"] == SG_ID and r["sd"] == sd and r["sg_typecode"] in TYPECODE_OFFICE:
                match = r
                break
        roster[key_str] = match or {}  # 빈 dict면 등록 후보 아님
        if match:
            n_match += 1
        if i % 50 == 0:
            print(f"  진행 {i}/{len(targets)} (신규 fetch {n_new}, 등록 match {n_match})", file=sys.stderr)
        time.sleep(0.15)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(roster, f, ensure_ascii=False, indent=2)
    matched_total = sum(1 for v in roster.values() if v)
    print(f"\n완료: 전체 {len(roster)} keys / 등록 후보 {matched_total}명 → {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
