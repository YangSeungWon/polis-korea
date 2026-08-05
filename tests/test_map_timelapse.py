"""지도 타임랩스 — **snapshot이 있다 ≠ 지금 polygon에 칠할 수 있다**를 지킨다.

포항 1995 도농통합은 세 층이 실제로 갈라지는지 확인하기 좋은 자리다:

    대선  1992 포항시 + 영일군 → 통합 포항시   합산 성립 (aggregated)
    총선  1992 포항시 + 영일군·울릉군 → 통합 포항시  울릉군이 밖에 있어 불가 (unavailable)

**같은 사건, 같은 날짜인데 series에 따라 답이 다르다.** series를 먼저 골라야 하는
이유가 여기 있다. 그리고 unavailable은 색을 만들지 않는다는 것까지 검사한다.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))

DOC = json.loads((ROOT / "data/map_timelapse/포항.json").read_text(encoding="utf-8"))
ROLES = ["before_election", "election", "before_geo_event", "after_geo_event",
         "next_election"]
MERGE = "geo:1995-01-01:pohang-merge"
fails: list = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        fails.append(f"{name}{' — ' + detail if detail else ''}")
        print(f"  ✗ {name}{' — ' + detail if detail else ''}")


def block(sid: str) -> dict:
    return next(b for b in DOC["series_blocks"] if b["comparison_series_id"] == sid)


def state(sid: str, role: str) -> dict:
    return next(s for s in block(sid)["states"] if s["role"] == role)


# ── 다섯 상태가 다 있고 순서가 맞는가 ──────────────────────────────────────
for b in DOC["series_blocks"]:
    sid = b["comparison_series_id"]
    ck(f"{sid}: 다섯 상태", [s["role"] for s in b["states"]] == ROLES,
       str([s["role"] for s in b["states"]]))
    ck(f"{sid}: 날짜 단조증가",
       [s["date"] for s in b["states"]] == sorted(s["date"] for s in b["states"]))
    # series를 섞지 않는다 — 프레임의 snapshot이 그 series 것이어야 한다
    ck(f"{sid}: snapshot이 같은 series",
       all(s["election_snapshot"]["comparison_series_id"] == sid for s in b["states"]))
    # 보간하지 않는다 — 각 시점은 그 이전 **실제** 선거를 쓴다
    ck(f"{sid}: snapshot 날짜 ≤ 시점",
       all(s["election_snapshot"]["date"] <= s["date"] for s in b["states"]))
    ck(f"{sid}: 모델과 경계 파일 일치",
       all(s["geography_at_date"]["model_matches_boundary"] for s in b["states"]))

# ── topology는 사건일에 **이산** 전환한다 ─────────────────────────────────
for sid in [b["comparison_series_id"] for b in DOC["series_blocks"]]:
    a, z = state(sid, "before_geo_event"), state(sid, "after_geo_event")
    ck(f"{sid}: 사건 직전 두 단위",
       a["geography_at_date"]["units"] == ["영일군", "포항시"],
       str(a["geography_at_date"]["units"]))
    ck(f"{sid}: 사건 직후 한 단위", z["geography_at_date"]["units"] == ["포항시"],
       str(z["geography_at_date"]["units"]))
    ck(f"{sid}: 전환은 하루 만에", a["date"] == "1994-12-31" and z["date"] == "1995-01-01",
       f"{a['date']}→{z['date']}")
    ck(f"{sid}: topology signature가 실제로 바뀐다",
       a["geography_at_date"]["topology_signature"]
       != z["geography_at_date"]["topology_signature"])
    # 이름만 갈아 끼우면 옛 폴리곤이 새 entity 행세를 한다. 면적이 그걸 잡는다 —
    # territorial_continuity=same_total이면 합이 보존돼야 한다.
    s0 = sum(a["geography_at_date"]["area_km2_approx"].values())
    s1 = sum(z["geography_at_date"]["area_km2_approx"].values())
    ck(f"{sid}: 통합 전후 면적 보존(same_total)", abs(s1 - s0) / s0 < 0.02,
       f"{s0} → {s1}")
    ck(f"{sid}: 통합 폴리곤이 옛 포항시가 아니다",
       s1 > a["geography_at_date"]["area_km2_approx"]["포항시"] * 5,
       f"{s1} vs {a['geography_at_date']['area_km2_approx']['포항시']}")

# ── 대선: 합산이 성립하고, **실제 합**인가 ────────────────────────────────
p = state("president:national", "after_geo_event")["political_projection"]["per_unit"]["포항시"]
ck("대선 통합 직후 aggregated", p["method"] == "aggregated", p["method"])
ck("합산 근거가 사건이다", MERGE in p["licensed_by"], str(p["licensed_by"]))
ck("합산 단위 = 포항시 + 영일군", p["source_units"] == ["영일군", "포항시"],
   str(p["source_units"]))

raw = json.loads((ROOT / "data/results/14th-pres-1992.json").read_text(encoding="utf-8"))
want: dict = {}
for r in raw["races"]:
    if r.get("scope") == "sigungu" and r.get("sigungu") in ("포항시", "영일군") \
            and r.get("sido") == "경상북도":
        for c in r["candidates"]:
            want[c["name"]] = want.get(c["name"], 0) + c["votes"]
got = {c["name"]: c["votes"] for c in p["candidates"]}
# 비율 배분이 아니라 **더하기**여야 한다. 하나라도 어긋나면 새 주장을 만든 것이다.
ck("합산이 원자료의 정확한 합", got == want,
   str({k: (want.get(k), got.get(k)) for k in set(want) | set(got)
        if want.get(k) != got.get(k)}))

nx = state("president:national", "next_election")["political_projection"]["per_unit"]["포항시"]
ck("1997 대선은 일반구 합산", nx["method"] == "aggregated", nx["method"])
ck("합산 근거가 포함관계다",
   any(x.startswith("contain:") for x in nx["licensed_by"]), str(nx["licensed_by"]))
ck("일반구 둘로 덮었다", nx["source_units"] == ["포항시남구", "포항시북구"],
   str(nx["source_units"]))

# ── 총선: 같은 사건인데 **투영이 안 된다** ────────────────────────────────
g = state("general:district", "after_geo_event")["political_projection"]["per_unit"]["포항시"]
ck("총선 통합 직후 unavailable", g["method"] == "unavailable", g["method"])
ck("사유는 경계 밖 단위", g["reason"] == "snapshot_unit_extends_beyond_target", g["reason"])
ck("울릉군을 지목한다", "울릉군" in json.dumps(g["detail"], ensure_ascii=False),
   json.dumps(g["detail"], ensure_ascii=False))
# 같은 날짜·같은 사건인데 series에 따라 답이 다르다 — 이게 series를 먼저 고르는 이유다
ck("같은 사건에서 series별 판정이 갈린다", p["method"] != g["method"])

# ── unavailable은 정치색을 만들지 않는다 ──────────────────────────────────
n_unav = 0
for b in DOC["series_blocks"]:
    for s in b["states"]:
        for name, pr in s["political_projection"]["per_unit"].items():
            if pr["method"] != "unavailable":
                ck(f"{s['state_id']}/{name}: 칠할 수 있으면 paint가 있다", "paint" in pr)
                continue
            n_unav += 1
            leaked = [k for k in ("paint", "winner", "candidates",
                                  "lineage_composition") if k in pr]
            ck(f"{s['state_id']}/{name}: 색·후보를 만들지 않는다", not leaked, str(leaked))
            ck(f"{s['state_id']}/{name}: 사유를 밝힌다", bool(pr.get("reason")))
ck("unavailable 사례가 실제로 있다", n_unav > 0, str(n_unav))

# 표시 불가 상태의 문장이 결과를 주장하지 않는다
gs = state("general:district", "after_geo_event")
ck("표시 불가는 문장도 그렇게 말한다", "표시할 수 없" in gs["displayable_claim"],
   gs["displayable_claim"])
ck("합산은 문장에 합산이라고 쓴다",
   "합산" in state("president:national", "after_geo_event")["displayable_claim"],
   state("president:national", "after_geo_event")["displayable_claim"])

# ── 이름이 아니라 id로 센다 ───────────────────────────────────────────────
from map_timelapse import Geo, footprint, tokenize_district  # noqa: E402

geo = Geo()
a = geo.resolve("포항시", "1992-12-18", "경상북도")["id"]
z = geo.resolve("포항시", "1997-12-18", "경상북도")["id"]
ck("같은 이름 다른 시점 = 다른 entity", a != z and a and z, f"{a} / {z}")
# 일반구는 후신이 아니다 — 상위 단위를 끝내면 안 된다
ck("포항시는 1995 이후로도 살아 있다",
   geo.ents["admin_unit:경상북도:포항시"].get("valid_to") is None)
fp, via = footprint(geo, "admin_unit:경상북도:포항시", "1992-12-18")
ck("1992로 되돌리면 두 단위", fp == {"admin_unit:경상북도:포항시(구)",
                                    "admin_unit:경상북도:영일군"}, str(fp))
fp2, _ = footprint(geo, "admin_unit:경상북도:포항시", "1997-12-18")
ck("사건 이후 시점은 되돌리지 않는다", fp2 == {"admin_unit:경상북도:포항시"}, str(fp2))

# 못 쪼개는 선거구명은 **추측하지 않는다**
ck("모르는 선거구는 None", tokenize_district("없는시갑", {"포항시", "울릉군"}) is None)
ck("아는 선거구는 쪼갠다",
   tokenize_district("영일군·울릉군", {"영일군", "울릉군"}) == ["영일군", "울릉군"])

# ── 합산 가능 판정을 여기서 만들지 않는다 ─────────────────────────────────
evs = {e["id"]: e for e in geo.events}
ck("합산은 territorial_continuity가 허락한 것만",
   evs[MERGE]["territorial_continuity"] in ("same", "same_total"),
   evs[MERGE]["territorial_continuity"])
ck("사건에 근거가 있다", bool(evs[MERGE].get("evidence")))
cont = json.loads((ROOT / "data/geography/containment.json").read_text(encoding="utf-8"))
ck("포함관계는 exhaustive일 때만 합산",
   all(c.get("exhaustive") is True and c.get("evidence")
       for c in cont["containments"]))

# ── 재생성이 같은 결과를 내는가 ───────────────────────────────────────────
before = (ROOT / "data/map_timelapse/포항.json").read_text(encoding="utf-8")
subprocess.run([sys.executable, "scripts/build/map_timelapse.py"], cwd=ROOT,
               check=True, capture_output=True)
ck("재생성 결과가 같다",
   (ROOT / "data/map_timelapse/포항.json").read_text(encoding="utf-8") == before)

print(f"\n[지도 타임랩스] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
