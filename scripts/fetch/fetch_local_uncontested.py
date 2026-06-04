"""지선 무투표 당선자 → results JSON inject (새 schema).

NEC OpenAPI WtvtelpcInfoInqireService/getWtvtelpcsccnInfoInqire:
  단독 후보 등록으로 무투표 당선된 후보 list. 개표 race API에는 row 자체가
  없어 매번 시군구·선거구 hex에 '데이터 없음'으로 표시됨.

지원 tc:
  3 광역단체장 · 4 기초단체장 · 5 광역의원 · 6 기초의원 · 11 교육감

API 응답 정상 시:
  data/raw/nec_uncontested/local_{n}.json 캐시 + results JSON race 추가.
  is_uncontested=True 플래그, votes=0, won=True.

API 미공개 시 (개표 직후 ~ 며칠):
  graceful skip. 기존 캐시 파일 있으면 그걸로 inject. 없으면 그냥 통과.

사용:
  NEC_API_KEY=... python3 scripts/fetch/fetch_local_uncontested.py --election 9th-local-2026
  python3 scripts/fetch/fetch_local_uncontested.py --election 8th-local-2022 --inject-only

새 회차 추가 시 build_local_pipeline.sh에 끼우면 자동.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ELECTIONS = ROOT / "data/elections"
RESULTS = ROOT / "data/results"
CACHE_DIR = ROOT / "data/raw/nec_uncontested"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

API = "https://apis.data.go.kr/9760000/WtvtelpcInfoInqireService/getWtvtelpcsccnInfoInqire"

TC_LABEL = {"3": "광역장", "4": "기초장", "5": "광역의원",
            "6": "기초의원", "11": "교육감"}
TC_SCOPE = {"3": "sido", "4": "sigungu", "5": "district",
            "6": "district", "11": "sido"}


def _load_key() -> str:
    key = os.environ.get("NEC_API_KEY")
    if key:
        return key
    env = ROOT / ".env"
    if env.exists():
        for ln in env.read_text(encoding="utf-8").splitlines():
            if ln.startswith("NEC_API_KEY="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def fetch_api(key: str, sg_id: str, tc: str) -> list[dict]:
    """무투표 후보 list 또는 빈 list (API 미공개)."""
    qs = urllib.parse.urlencode({
        "serviceKey": key, "sgId": sg_id, "sgTypecode": tc,
        "pageNo": 1, "numOfRows": 1000,
    })
    try:
        with urllib.request.urlopen(f"{API}?{qs}", timeout=20) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print(f"  ! {TC_LABEL[tc]} fetch 실패: {e}", file=sys.stderr)
        return []
    code = root.findtext(".//resultCode")
    if code != "INFO-00":
        return []
    out = []
    for it in root.findall(".//item"):
        out.append({
            "sg_typecode": tc,
            "sido": it.findtext("sdName") or "",
            "sgg_name": it.findtext("sggName") or "",
            "wiw_name": it.findtext("wiwName") or "",
            "name": it.findtext("name") or "",
            "party": it.findtext("jdName") or "",
        })
    return out


def to_race(item: dict) -> dict:
    """API item → 새 schema race."""
    tc = item["sg_typecode"]
    scope = TC_SCOPE[tc]
    race = {
        "sg_typecode": tc,
        "sido": item["sido"],
        "sigungu": "",
        "scope": scope,
        "electors": 0,
        "voters": 0,
        "valid_votes": 0,
        "invalid_votes": 0,
        "abstain": 0,
        "count_pct": 100.0,
        "is_uncontested": True,
        "candidates": [{
            "name": item["name"],
            "party": item["party"],
            "votes": 0,
            "pct": 0.0,
            "rank": 1,
            "won": True,
            "uncontested": True,
        }],
    }
    if tc == "4":  # 기초장: sgg_name=시군구
        race["sigungu"] = item["sgg_name"]
    elif tc in ("5", "6"):  # 의원: sgg_name=선거구, wiw_name=시군구
        race["district"] = item["sgg_name"]
        race["sigungu"] = item["wiw_name"]
    # tc 3/11: sido scope, sigungu/district 비움
    return race


def inject(election_id: str, items: list[dict]) -> int:
    """results 새 schema에 race 추가 (main + .sigungu chunk 자동 분기)."""
    if not items:
        return 0
    main_path = RESULTS / f"{election_id}.json"
    sub_path = RESULTS / f"{election_id}.sigungu.json"
    if not main_path.exists():
        print(f"  ! {main_path.name} 없음 — fetch_nec_live 먼저 실행", file=sys.stderr)
        return 0
    main = json.loads(main_path.read_text(encoding="utf-8"))
    sub = json.loads(sub_path.read_text(encoding="utf-8")) if sub_path.exists() else None

    # 기존 race와 중복 제거 (sg_typecode + sido + sigungu/district 키)
    def race_key(r):
        return (r.get("sg_typecode"), r.get("sido"), r.get("sigungu", ""), r.get("district", ""))
    main_keys = {race_key(r) for r in main.get("races", [])}
    sub_keys = {race_key(r) for r in (sub.get("races") or [])} if sub else set()
    all_keys = main_keys | sub_keys

    added = 0
    for item in items:
        race = to_race(item)
        if race_key(race) in all_keys:
            continue  # 이미 있음 (개표 진행도 100% 도달했지만 어쩌면 raw에도 등록)
        # main(광역/교육감) vs sub(나머지) 분기 — chunk_results.py 규칙과 동일
        if race["scope"] in ("nation", "sido"):
            main["races"].append(race)
        elif race["sg_typecode"] in ("5", "6") and race["scope"] == "district":
            if sub: sub["races"].append(race)
            else: main["races"].append(race)
        elif race["scope"] in ("sigungu", "district_sigungu", "sigungu_part"):
            if sub: sub["races"].append(race)
            else: main["races"].append(race)
        else:
            main["races"].append(race)
        added += 1

    if added:
        main_path.write_text(json.dumps(main, ensure_ascii=False, indent=2), encoding="utf-8")
        if sub:
            sub_path.write_text(json.dumps(sub, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--election", required=True, help="data/elections/{id}.json")
    ap.add_argument("--inject-only", action="store_true",
                    help="API 호출 안 하고 기존 캐시로만 inject")
    args = ap.parse_args()

    meta_path = ELECTIONS / f"{args.election}.json"
    if not meta_path.exists():
        print(f"ERR: 메타 없음 — {meta_path}", file=sys.stderr)
        sys.exit(1)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    sg_id = (meta.get("nec") or {}).get("sg_id", "")
    if not sg_id:
        print("ERR: nec.sg_id 없음", file=sys.stderr)
        sys.exit(1)

    cache_path = CACHE_DIR / f"{args.election}.json"
    items = []

    if not args.inject_only:
        key = _load_key()
        if not key:
            print("ERR: NEC_API_KEY 없음", file=sys.stderr)
            sys.exit(1)
        print(f"=== {meta['name']} 무투표 fetch (sg_id={sg_id}) ===", file=sys.stderr)
        all_tcs = [o["sg_typecode"] for o in meta.get("offices", [])
                   if o["sg_typecode"] in TC_LABEL]
        for tc in all_tcs:
            got = fetch_api(key, sg_id, tc)
            items.extend(got)
            print(f"  ✓ tc={tc} {TC_LABEL[tc]}: {len(got)}건", file=sys.stderr)
        if items:
            cache_path.write_text(json.dumps(items, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
            print(f"  캐시 저장 → {cache_path.name}", file=sys.stderr)
        else:
            print("  API에 데이터 없음 (개표 직후 미공개 가능).", file=sys.stderr)
            if cache_path.exists():
                items = json.loads(cache_path.read_text(encoding="utf-8"))
                print(f"  기존 캐시 사용 ({len(items)}건)", file=sys.stderr)
    else:
        if cache_path.exists():
            items = json.loads(cache_path.read_text(encoding="utf-8"))
            print(f"캐시 로드: {len(items)}건", file=sys.stderr)
        else:
            print(f"캐시 없음 — {cache_path}", file=sys.stderr)
            sys.exit(0)

    if not items:
        print("inject 대상 없음. 종료.", file=sys.stderr)
        return

    added = inject(args.election, items)
    print(f"\n→ {args.election}: {added}건 inject", file=sys.stderr)


if __name__ == "__main__":
    main()
