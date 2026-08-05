"""선거구 geometry 빌드 파이프라인 — 회차 하나가 몰래 다른 방식을 쓰지 않는가.

**성공한 빌드 ≠ 동질적인 입력.**

20대만 `mode="wwolf"`였다. 빌드는 매번 성공했고 파일도 멀쩡했다. 그런데 9~19·21·22가
전부 `nec_emd`인데 혼자 다른 파이프라인이라 폴리곤이 어긋났고, 그게 21↔20 계보
판정에서 125개를 '출처가 다르다'로 보류시킨 원인이었다.
바로잡으니 겹침 중앙값 93.9% → 99.6%, 비교 가능 54 → 204가 됐다.

밖에서 원본 데이터를 찾을 게 아니라 안에서 예외를 찾았어야 했다. 그래서 예외를
**명시적 allowlist**로만 허용하고, 새 이탈이 생기면 여기서 잡는다.

실행: .venv/bin/python tests/test_geometry_pipeline.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
from build_district_geojson import CFG  # noqa: E402

# 회차별 기대 모드. 예외는 **여기에 이유와 함께** 적는다 — 코드에 조용히 두지 않는다.
EXPECTED = "nec_emd"
ALLOWED_EXCEPTIONS = {
    # NEC 투표구별 자료가 8대 이전에는 없다 → 시군구 경계 union으로 근사.
    # 근사임을 properties의 approx로 스스로 밝힌다.
    8: "sgg_union",
}
LEGACY_KEYS = {"20_wwolf_legacy"}   # 보존용 — 실제 빌드 대상이 아니다

fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    rounds = {k: v for k, v in CFG.items() if isinstance(k, int)}
    print(f"\n[모드] 회차 {len(rounds)}개")
    drift = []
    for n, cfg in sorted(rounds.items()):
        want = ALLOWED_EXCEPTIONS.get(n, EXPECTED)
        if cfg.get("mode") != want:
            drift.append(f"{n}대: {cfg.get('mode')} (기대 {want})")
    ck("회차별 빌드 모드가 기대와 일치", not drift, str(drift))
    ck("예외는 allowlist에만 있다",
       all(n in ALLOWED_EXCEPTIONS or c.get("mode") == EXPECTED
           for n, c in rounds.items()))
    ck("legacy 키는 정수 회차가 아니다 (빌드 대상 아님)",
       all(isinstance(k, str) for k in CFG if k in LEGACY_KEYS))

    print("\n[입력] 같은 모드면 같은 계열의 입력을 쓰는가")
    nec = {n: c for n, c in rounds.items() if c.get("mode") == "nec_emd"}
    missing_emd = [n for n, c in nec.items() if not (c.get("emd") or Path()).exists()]
    ck(f"nec_emd 회차 {len(nec)}개의 읍면동 매핑이 전부 있다",
       not missing_emd, str(missing_emd))
    missing_shp = [n for n, c in nec.items() if not (c.get("shp") or Path()).exists()]
    ck("동 경계 shapefile이 전부 있다", not missing_shp, str(missing_shp))

    print("\n[산출물] 지문이 모드와 맞는가")
    sys.path.insert(0, str(ROOT / "scripts/normalize"))
    from build_district_lineage import source_profile
    prof = {}
    for n in sorted(rounds):
        p = source_profile(n)
        if p:
            prof[n] = p
    # 같은 모드 · 인접 회차면 지문이 같아야 한다 — 다르면 입력 계열이 어긋난 것이다
    odd = []
    ns = sorted(prof)
    for i in range(1, len(ns)):
        a, b = ns[i - 1], ns[i]
        if rounds[a].get("mode") != rounds[b].get("mode"):
            continue
        # 정밀도가 다르면 입력 shapefile 계열이 다르다는 뜻
        if prof[a][1] != prof[b][1]:
            odd.append(f"{a}↔{b}: 정밀도 {prof[a][1]} vs {prof[b][1]}")
    ck("같은 모드의 인접 회차는 좌표 정밀도가 같다", not odd, str(odd[:3]))

    print("\n[계보] 파이프라인 이탈이 판정 보류로 새지 않는가")
    lin = ROOT / "data/district_lineage/21__20.json"
    if lin.exists():
        d = json.loads(lin.read_text(encoding="utf-8"))
        unk = d["counts"].get("comparable_unknown", 0)
        # wwolf 시절 125건이었다. 같은 파이프라인이 되면 크게 줄어야 한다.
        ck(f"21↔20 판정 보류가 30건 미만 ({unk})", unk < 30, str(unk))
        ck(f"21↔20 비교 가능이 150곳 이상 ({d['counts']['comparable']})",
           d["counts"]["comparable"] >= 150, str(d["counts"]["comparable"]))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
