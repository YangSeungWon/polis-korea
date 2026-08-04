"""잠정(라이브) 결과 → NEC OpenAPI 확정본 승격. 선거 생애주기 2단계.

개표 당일엔 info.nec.go.kr 라이브로 잠정 결과를 띄우지만, NEC OpenAPI는 몇 주~두 달
뒤에야 확정 데이터를 게시한다. 그 사이를 잇는 단계가 없어서 9회 지선 잠정 파일이 두 달
방치됐고, 그 틈에 daily의 부분 갱신이 데이터를 깨뜨렸다(2026-07-31). 이 스크립트가
'게시됐는지 확인 → 전면 재fetch → 손실 없는지 검증 → is_final' 을 한 번에 한다.

안전 규칙 (2026-07-31 사고에서 도출):
  1. 부분 결과로 덮어쓰지 않는다 — fetch 실패·급감 시 fetch_nec_results가 중단한다.
  2. OpenAPI가 주지 않는 직(광역/기초 비례 tc8·tc9)은 이전 파일에서 이관한다.
     'fetch 후 사라진 sg_typecode'를 일반 규칙으로 이관하므로 직 목록을 하드코딩하지 않는다.
  3. 승격 전후를 대조해 race·후보·당선자가 **하나라도 줄면 롤백**한다.

사용:
  python3 scripts/build/finalize_election.py --election 9th-byelection-2026
  python3 scripts/build/finalize_election.py --auto          # 최근 미확정 회차 자동
  python3 scripts/build/finalize_election.py --auto --dry-run
"""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ELECTIONS_DIR = ROOT / "data/elections"
RESULTS_DIR = ROOT / "data/results"
PROBE = ("https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2"
         "/getXmntckSttusInfoInqire")

# 승격 후 추가로 돌려야 하는 회차별 보정 단계 (라이브 명부 오버레이).
# 개표 API엔 무투표·중선거구 당선·비례 의석이 없어 이 단계 없이는 결손이 남는다.
POST_STEPS = {
    "9th-local-2026": [
        ["scripts/fetch/fetch_single_winners_live.py"],
        ["scripts/fetch/fetch_council_winners_live.py"],
    ],
}
# 이 회차 모양인데 보정 단계가 없으면 조용히 결손이 생긴다 — 명시적으로 막는다.
NEEDS_POST = ("5", "6", "8", "9")

# 주 scope — 검증은 부분집계가 아닌 실제 race 단위로 한다.
MAIN_SCOPE = {"1": "nation", "2": "district", "3": "sido", "4": "sigungu",
              "5": "district", "6": "district", "7": "nation", "11": "sido",
              "8": "proportional_sido", "9": "proportional_sigungu"}


def _load_api_key() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("NEC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    import os
    return os.environ.get("NEC_API_KEY", "")


def published(key: str, sg_id: str, tc: str, sidos: list[str]) -> bool:
    """OpenAPI가 그 선거를 게시했는지 — 한 시도라도 INFO-00이면 확정 데이터 있음.

    개표 API는 sdName이 필수라 시도를 찍어야 하는데, 재보궐은 치러진 시도가 몇 곳뿐이라
    '서울' 같은 고정값으로 물으면 INFO-03이 와서 미게시로 오판한다. 그래서 지금 가지고
    있는 잠정 결과에 실제로 등장하는 시도로 묻는다.
    """
    for sd in sidos[:6]:
        url = (f"{PROBE}?serviceKey={key}&sgId={sg_id}&sgTypecode={tc}"
               f"&sdName={urllib.parse.quote(sd)}&pageNo=1&numOfRows=1&resultType=xml")
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                root = ET.fromstring(r.read().decode("utf-8", errors="replace"))
        except Exception as e:
            print(f"  ! probe 실패({sd}): {e}", file=sys.stderr)
            continue
        if root.findtext(".//resultCode") == "INFO-00":
            return True
    return False


def profile(doc: dict) -> dict:
    """(tc, 주 scope)별 race·후보·당선자 수 — 승격 전후 대조용."""
    out: dict[str, Counter] = {}
    for r in doc.get("races", []):
        tc = r.get("sg_typecode")
        if r.get("scope") != MAIN_SCOPE.get(tc):
            continue
        c = out.setdefault(tc, Counter())
        c["races"] += 1
        cands = r.get("candidates") or []
        c["candidates"] += len(cands)
        c["winners"] += sum(1 for x in cands if x.get("won"))
    return out


def candidates_for_auto() -> list[str]:
    """최근 1년 내 치러졌는데 아직 확정이 아닌 회차. 옛 회차(위키 출처 등)는 제외."""
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    out = []
    for p in sorted(ELECTIONS_DIR.glob("*.json")):
        meta = json.loads(p.read_text(encoding="utf-8"))
        if not (meta.get("nec") or {}).get("sg_id"):
            continue
        if (meta.get("date") or "") < cutoff:
            continue
        rp = RESULTS_DIR / f"{meta['id']}.json"
        if not rp.exists():
            continue
        try:
            m = json.loads(rp.read_text(encoding="utf-8")).get("_meta", {})
        except Exception:
            continue
        if not m.get("is_final"):
            out.append(meta["id"])
    return out


def run(cmd: list[str]) -> bool:
    print(f"    $ {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run([sys.executable] + cmd, cwd=ROOT).returncode == 0


def finalize(eid: str, key: str, dry: bool) -> bool:
    meta = json.loads((ELECTIONS_DIR / f"{eid}.json").read_text(encoding="utf-8"))
    sg_id = (meta.get("nec") or {}).get("sg_id")
    rp = RESULTS_DIR / f"{eid}.json"
    before = json.loads(rp.read_text(encoding="utf-8"))

    tcs = [o["sg_typecode"] for o in meta.get("offices", [])]
    probe_tc = next((t for t in ("3", "2", "1", "4", "11") if t in tcs), tcs[0])
    sidos = [s for s in dict.fromkeys(r.get("sido") for r in before["races"]
                                      if r.get("sg_typecode") == probe_tc) if s]
    if probe_tc == "1":          # 대선은 전국 합계 row
        sidos = ["합계"] + sidos
    if not published(key, sg_id, probe_tc, sidos or ["서울특별시"]):
        print(f"  {eid}: OpenAPI 미게시 — 다음 주기 재시도", file=sys.stderr)
        return True
    print(f"  {eid}: OpenAPI 게시 확인 → 확정 승격 시작", file=sys.stderr)

    need_post = any(t in NEEDS_POST for t in tcs)
    if need_post and eid not in POST_STEPS:
        print(f"  ✗ {eid}: 지방의원·비례(tc {NEEDS_POST})가 있는데 보정 단계가 등록되지 "
              f"않았다. POST_STEPS에 추가하기 전엔 승격하지 않는다(결손 방지).",
              file=sys.stderr)
        return False
    if dry:
        print(f"    [dry] 재fetch + 보정 {len(POST_STEPS.get(eid, []))}단계 + 검증",
              file=sys.stderr)
        return True

    snap = Path(tempfile.mkdtemp()) / "before.json"
    shutil.copy(rp, snap)
    try:
        if not run(["scripts/fetch/fetch_nec_results.py", "--election", eid]):
            print("  ✗ 재fetch 실패 — 원본 유지", file=sys.stderr)
            shutil.copy(snap, rp)
            return False

        # OpenAPI가 주지 않는 직은 이전 파일에서 이관 (tc8·tc9 비례 등).
        after = json.loads(rp.read_text(encoding="utf-8"))
        have = {r.get("sg_typecode") for r in after["races"]}
        carried = [r for r in before["races"] if r.get("sg_typecode") not in have]
        if carried:
            kinds = sorted({r.get("sg_typecode") for r in carried})
            after["races"].extend(carried)
            after["_meta"]["carried_from_live"] = {
                "sg_typecodes": kinds,
                "reason": "OpenAPI 개표 API 미제공 — 직전 라이브 산출물 이관",
            }
            rp.write_text(json.dumps(after, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
            print(f"    이관: tc{'·'.join(kinds)} {len(carried)} races", file=sys.stderr)

        for step in POST_STEPS.get(eid, []):
            if not run(step):
                print("  ✗ 보정 단계 실패 — 롤백", file=sys.stderr)
                shutil.copy(snap, rp)
                return False

        # 검증 — 하나라도 줄면 롤백.
        pb, pa = profile(before), profile(json.loads(rp.read_text(encoding="utf-8")))
        bad = []
        for tc in sorted(set(pb) | set(pa)):
            b, a = pb.get(tc, Counter()), pa.get(tc, Counter())
            for k in ("races", "candidates", "winners"):
                if a[k] < b[k]:
                    bad.append(f"tc{tc}.{k}: {b[k]} → {a[k]}")
            if b or a:
                mark = "→" if a != b else "="
                print(f"    tc{tc}: race {b['races']}{mark}{a['races']} · "
                      f"후보 {b['candidates']}{mark}{a['candidates']} · "
                      f"당선 {b['winners']}{mark}{a['winners']}", file=sys.stderr)
        if bad:
            print("  ✗ 승격 후 데이터 감소 — 롤백:", file=sys.stderr)
            for x in bad:
                print(f"      {x}", file=sys.stderr)
            shutil.copy(snap, rp)
            return False

        doc = json.loads(rp.read_text(encoding="utf-8"))
        # race 순서를 고정한다. fetch·이관·보정이 각자 다른 위치에 끼워 넣어서, 내용이
        # 완전히 같아도 실행마다 순서가 달라져 승격 diff가 18만 줄로 부풀고 검토가 불가능해진다.
        # 마지막 항은 동률 제거용 — 정렬을 전순서로 만들어 실행 간 재현성을 보장한다.
        doc["races"].sort(key=lambda r: (
            r.get("sg_typecode") or "", r.get("scope") or "", r.get("sido") or "",
            r.get("sigungu") or "", r.get("district") or "",
            json.dumps(r, sort_keys=True, ensure_ascii=False)))
        doc["_meta"]["is_final"] = True
        doc["_meta"].pop("source", None)
        rp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
        print(f"  ✓ {eid} 확정 승격 완료 (is_final: true)", file=sys.stderr)
        return True
    finally:
        shutil.rmtree(snap.parent, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--election", help="회차 id")
    g.add_argument("--auto", action="store_true", help="최근 1년 내 미확정 회차 전부")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = _load_api_key()
    if not key:
        print("ERR: NEC_API_KEY 미설정", file=sys.stderr)
        sys.exit(1)

    eids = [args.election] if args.election else candidates_for_auto()
    if not eids:
        print("확정 대기 중인 회차 없음 — 할 일 없음", file=sys.stderr)
        return
    print(f"=== 확정 승격 대상 {len(eids)}건: {', '.join(eids)} ===", file=sys.stderr)

    ok = True
    for eid in eids:
        if not finalize(eid, key, args.dry_run):
            ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
