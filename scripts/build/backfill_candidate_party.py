"""후보 정당 백필 — 조사 PDF에 정당이 안 적힌 후보의 공식 정당을 NEC API로 채움.

build_polls의 자동 다수결은 "어느 조사에도 정당이 안 적힌 후보"는 못 채운다(회색).
NEC 후보자 통합검색(CndaSrchService, 이름 기반)으로 공식 정당을 받아 캐시 →
build_polls가 빈 정당 보완에 사용.

흐름:
  1. aggregated.json에서 정당 빈 + 실명형(2~4 한글) (sido, name) 수집.
  2. 이름별로 CndaSrchService 조회 (한 번에 그 이름의 모든 출마 이력). 동명이인은 sdName 매칭.
  3. (sido|name)→정당 캐시 → data/raw/nec_candidate_party.json (공개데이터, 커밋 가능).
  캐시에 이미 있는 이름은 skip (멱등·증분).

사용:
  NEC_API_KEY=... .venv/bin/python scripts/build/backfill_candidate_party.py        # API 조회→캐시
  .venv/bin/python scripts/build/backfill_candidate_party.py --offline               # 캐시만 (조회 X)
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGG = ROOT / "data" / "polls" / "aggregated.json"
CACHE = ROOT / "data" / "raw" / "nec_candidate_party.json"
OFFICE_CACHE = ROOT / "data" / "raw" / "nec_candidate_office.json"
API = "https://apis.data.go.kr/9760000/CndaSrchService/getCndaSrchInqire"

# NEC sgTypecode → office_level (관심 직위만; 5=광역의원·6=기초의원 등은 무시)
TYPECODE_OFFICE = {"3": "광역단체장", "4": "기초단체장", "11": "교육감"}


def resolve_office(rows: list[dict], sido: str) -> str:
    """2026 지방선거 + 해당 sido 등록 이력의 sgTypecode로 office_level 결정.
    관심 직위(광역단체장·기초단체장·교육감)가 유일하게 좁혀질 때만 반환 (동명이인 안전)."""
    offs = {TYPECODE_OFFICE[r["tc"]] for r in rows
            if r["sgId"].startswith(TARGET_SG) and r["sd"] == sido and r["tc"] in TYPECODE_OFFICE}
    return offs.pop() if len(offs) == 1 else ""


def fetch_name(key: str, name: str) -> list[dict]:
    """그 이름의 모든 출마 이력 (sdName·sggName·jdName·sgId)."""
    url = f"{API}?serviceKey={key}&name={urllib.parse.quote(name)}&pageNo=1&numOfRows=100"
    try:
        root = ET.fromstring(urllib.request.urlopen(url, timeout=30).read())
    except Exception as e:
        print(f"  ! {name}: {e}", file=sys.stderr)
        return []
    if root.findtext("header/resultCode") != "INFO-00":
        return []
    out = []
    for it in root.findall("body/items/item"):
        out.append({
            "sd": it.findtext("sdName") or "",
            "jd": it.findtext("jdName") or "",
            "sgId": it.findtext("sgId") or "",
            "tc": it.findtext("sgTypecode") or "",   # 3=광역단체장 4=기초단체장 11=교육감
        })
    return out


# 2026 현존 정당만 신뢰 (폐지 정당=동명이인/옛 이력 → 2026 후보에 붙이면 오류)
CURRENT_PARTIES = {
    "더불어민주당", "민주당", "국민의힘", "조국혁신당", "개혁신당", "진보당",
    "기본소득당", "새로운미래", "사회민주당", "녹색정의당", "무소속",
}


TARGET_SG = "2026"  # 9회 지방선거(sgId 2026…) — 다선 경력자의 옛 선거 정당 오매칭 방지


def resolve(rows: list[dict], sido: str) -> str:
    """sido 매칭 동명이인 구분 → 정당. 2026 지방선거 등록 이력을 최우선으로,
    없으면(예비·미등록) 가장 최근 이력으로 fallback. 현존 정당만 (옛 정당=오매칭→'')."""
    cand = [r for r in rows if r["sd"] == sido] or rows
    if not cand:
        return ""
    # 2026 등록 이력이 있으면 그것만 — 김관영(과거 무소속 국회의원 이력)류 오매칭 차단
    cur = [r for r in cand if r["sgId"].startswith(TARGET_SG)]
    pool = sorted(cur or cand, key=lambda r: r["sgId"], reverse=True)
    party = pool[0]["jd"] or "무소속"
    return party if party in CURRENT_PARTIES else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--refresh", action="store_true",
                    help="캐시의 모든 이름을 재조회·재해결 (resolve 로직 변경 시 기존 오매칭 교정)")
    ap.add_argument("--diag", metavar="NAME",
                    help="한 이름의 NEC 원본 이력(sgId·sido·정당) 출력 후 종료")
    args = ap.parse_args()

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    ocache = json.loads(OFFICE_CACHE.read_text(encoding="utf-8")) if OFFICE_CACHE.exists() else {}

    # 진단: 한 이름의 raw 이력만 보고 종료
    if args.diag:
        key = os.environ.get("NEC_API_KEY")
        if not key:
            print("NEC_API_KEY 없음", file=sys.stderr); sys.exit(1)
        for r in sorted(fetch_name(key, args.diag), key=lambda x: x["sgId"], reverse=True):
            print(f"  sgId={r['sgId']} tc={r['tc']} {r['sd']} 정당={r['jd'] or '(무)'}")
        return

    recs = json.loads(AGG.read_text(encoding="utf-8"))["polls"]
    missing = set()       # 정당 빈 (sido, name)
    office_need = set()    # office 모를 race 후보 (sido, name) — "기타" 폴 등
    for r in recs:
        if r.get("is_self_poll"):
            continue
        gita = r.get("office_level") == "기타"
        sido = r.get("sido") or ""
        for c in r.get("candidates") or []:
            nm = (c.get("name") or "").strip()
            if not re.fullmatch(r"[가-힣]{2,4}", nm):
                continue
            if not c.get("party"):
                missing.add((sido, nm))
            if gita and c.get("pct") is not None:
                office_need.add((sido, nm))

    # --refresh: 캐시의 모든 이름 재조회. 기본: party·office 캐시에 없는 신규만.
    if args.refresh:
        todo_names = sorted({nm for _, nm in missing | office_need}
                            | {k.split("|", 1)[1] for k in cache}
                            | {k.split("|", 1)[1] for k in ocache})
    else:
        todo_names = sorted(
            {nm for s, nm in missing if f"{s}|{nm}" not in cache}
            | {nm for s, nm in office_need if f"{s}|{nm}" not in ocache})
    print(f"정당 빈 {len(missing)} · office 필요 {len(office_need)} | 조회할 이름: {len(todo_names)}"
          f"{' [refresh]' if args.refresh else ''}", file=sys.stderr)

    if args.offline or not todo_names:
        print("  (조회 생략 — offline 또는 신규 없음)" if args.offline else "  (신규 이름 없음)", file=sys.stderr)
    else:
        key = os.environ.get("NEC_API_KEY")
        if not key:
            print("  NEC_API_KEY 없음 → 조회 불가 (캐시만 사용하려면 --offline)", file=sys.stderr)
            sys.exit(1)
        by_name: dict[str, list[dict]] = {}
        for i, nm in enumerate(todo_names):
            by_name[nm] = fetch_name(key, nm)
            time.sleep(0.12)  # graceful
            if (i + 1) % 50 == 0:
                print(f"  ...{i + 1}/{len(todo_names)}", file=sys.stderr)
        # (sido|name) → party / office 해결. refresh면 기존 항목도 재해결.
        ptargets = set(missing) | ({(k.split("|", 1)[0], k.split("|", 1)[1]) for k in cache} if args.refresh else set())
        otargets = set(office_need) | ({(k.split("|", 1)[0], k.split("|", 1)[1]) for k in ocache} if args.refresh else set())
        n_new = n_chg = 0
        for sido, nm in sorted(ptargets):
            if nm not in by_name:
                continue
            party = resolve(by_name[nm], sido)
            if not party:
                continue
            k = f"{sido}|{nm}"
            if k not in cache:
                cache[k] = party; n_new += 1
            elif cache[k] != party:
                print(f"  교정 {k}: {cache[k]} → {party}", file=sys.stderr); cache[k] = party; n_chg += 1
        on_new = 0
        for sido, nm in sorted(otargets):
            if nm not in by_name:
                continue
            off = resolve_office(by_name[nm], sido)
            if off and ocache.get(f"{sido}|{nm}") != off:
                ocache[f"{sido}|{nm}"] = off; on_new += 1
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        OFFICE_CACHE.write_text(json.dumps(ocache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(f"  party 캐시 +{n_new} 교정 {n_chg} (총 {len(cache)}) · office 캐시 +{on_new} (총 {len(ocache)})", file=sys.stderr)

    fillable = sum(1 for s, n in missing if f"{s}|{n}" in cache)
    o_fill = sum(1 for s, n in office_need if f"{s}|{n}" in ocache)
    print(f"party 채움 {fillable}/{len(missing)} · office 채움 {o_fill}/{len(office_need)}")


if __name__ == "__main__":
    main()
