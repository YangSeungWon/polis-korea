"""9회 지선 등록 후보자 명부 fetch — NEC CndaSrchService.

CndaSrchService는 list endpoint 없고 name parameter 필수. polls에 등장한 후보들의 이름을
NEC API에 name으로 조회 → sgId=20260603 + sgTypecode (3/4/11) 매칭만 저장.

저장: data/raw/nec_roster_9th.json = {(sido, name): {sgg, jd, sg_typecode}}
산점도·hex의 "최종 등록 후보" 식별에 사용.

사용:
  NEC_API_KEY=... .venv/bin/python scripts/fetch/fetch_nec_roster.py
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

ROOT = Path(__file__).resolve().parents[2]
PARSED_DIR = ROOT / "data" / "raw" / "parsed"
API = "https://apis.data.go.kr/9760000/CndaSrchService/getCndaSrchInqire"
# build_polls의 시도 canonical 재사용 — roster 키를 build의 p["sido"]와 일치시키고,
# NEC 응답의 시대별 명칭(2018 강원도 ↔ 2026 강원특별자치도)을 canon으로 흡수.
sys.path.insert(0, str(ROOT / "scripts" / "build"))
from build_polls import canon_sido  # noqa: E402

# sgTypecode → office_level
TYPECODE_OFFICE = {"2": "국회의원", "3": "광역단체장", "4": "기초단체장", "11": "교육감"}


def _load_api_key() -> str:
    k = os.environ.get("NEC_API_KEY")
    if k:
        return k
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("NEC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


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
    import argparse
    ap = argparse.ArgumentParser(description="NEC 등록후보 명부 fetch (CndaSrchService)")
    ap.add_argument("--sg-id", default="20260603", help="선거 sgId (예: 20180613=7회 지선)")
    ap.add_argument("--csv", default="data/raw/nesdc_9th_polls.csv", help="NESDC 메타 CSV")
    ap.add_argument("--out", default="data/raw/nec_roster_9th.json", help="출력 roster JSON")
    ap.add_argument("--agg", default="data/polls/aggregated.json", help="aggregated.json (있으면 보충)")
    args = ap.parse_args()
    SG_ID = args.sg_id
    META_CSV = ROOT / args.csv
    OUT = ROOT / args.out
    AGG = ROOT / args.agg

    key = _load_api_key()
    if not key:
        print("NEC_API_KEY 필요 (env 또는 .env)", file=sys.stderr)
        sys.exit(1)
    # parsed JSON + meta region에서 (sido, name) 모음 — aggregated보다 광범위
    # (build_polls가 drop한 record의 후보도 포함되어 순환 의존 회피)
    import re, csv
    targets: set[tuple[str, str]] = set()

    # meta에서 ntt_id → sido (region 첫 토큰 canon — 단축형 "충북"·"경기"도 처리)
    ntt_to_sido = {}
    if META_CSV.exists():
        for r in csv.DictReader(open(META_CSV, encoding="utf-8")):
            toks = (r.get("region", "") or "").split()
            if toks:
                sd = canon_sido(toks[0])
                if sd:
                    ntt_to_sido[r["ntt_id"]] = sd

    if PARSED_DIR.exists():
        for path in PARSED_DIR.glob("*.json"):
            try:
                d = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            sd = ntt_to_sido.get(d.get("ntt_id", ""), "")
            if not sd:
                continue
            for q in d.get("questions", []):
                for c in q.get("candidates", []):
                    nm = (c.get("name") or "").strip()
                    if not nm or not re.fullmatch(r"[가-힣]{2,4}", nm):
                        continue
                    targets.add((sd, nm))

    # byelection.json도 보충 — 재보궐 후보 (sg_typecode=2)
    BYELECT = ROOT / "data" / "polls" / "byelection.json"
    if BYELECT.exists():
        try:
            bj = json.load(open(BYELECT, encoding="utf-8"))
            for d in bj.get("districts", []):
                # district 이름에서 sido 추출 (예: "부산 북구갑" → "부산광역시")
                SIDO_FROM_SHORT = {"서울":"서울특별시","부산":"부산광역시","대구":"대구광역시",
                    "인천":"인천광역시","광주":"광주광역시","대전":"대전광역시","울산":"울산광역시",
                    "세종":"세종특별자치시","경기":"경기도","강원":"강원특별자치도",
                    "충북":"충청북도","충남":"충청남도","전북":"전북특별자치도","전남":"전라남도",
                    "경북":"경상북도","경남":"경상남도","제주":"제주특별자치도"}
                first = (d.get("district") or "").split()[0] if d.get("district") else ""
                sd = SIDO_FROM_SHORT.get(first, "")
                if not sd: continue
                for p in d.get("polls", []):
                    for c in p.get("candidates", []):
                        nm = (c.get("name") or "").strip()
                        if not nm or not re.fullmatch(r"[가-힣]{2,4}", nm):
                            continue
                        targets.add((sd, nm))
        except Exception:
            pass

    # aggregated.json도 보충 (있으면)
    if AGG.exists():
        data = json.load(open(AGG, encoding="utf-8"))
        for p in data.get("polls", []):
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
        # 매칭된 entry({sg_typecode:..}) 있으면 skip. 빈 dict는 refetch (TYPECODE_OFFICE 확장 시).
        if key_str in roster and roster[key_str]:
            continue
        rows = fetch_name(key, nm)
        n_new += 1
        # sgId=20260603 + sd 매칭 + sgTypecode in 3/4/11
        match = None
        for r in rows:
            # NEC sdName을 canon으로 정규화해 시대별 명칭차(강원도↔강원특별자치도) 흡수
            if r["sg_id"] == SG_ID and canon_sido(r["sd"]) == sd and r["sg_typecode"] in TYPECODE_OFFICE:
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
