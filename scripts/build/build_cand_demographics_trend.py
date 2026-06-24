#!/usr/bin/env python3
"""차기주자(후보지지) 성×연령 '상시 추이' served 데이터 — 선거 비종속 연속 시계열.

입력:
  data/raw/parsed/cand_demographics.json   (extract_cand_demographics, ntt→성연령 후보지지)
  data/polls/aggregated_*.json (union)       (ntt→period_end, agency, sido)
출력:
  data/polls/cand_demographics_trend.json
    { _meta, groups: { "성별|남성":[{date,agency,c:[{name,party,pct}]}], "연령|30":[...], "남성|18-29":[...] } }

정당지지 추이(build_party_demographics_trend)의 차기주자 버전. 전국 + 다자(실제 후보 ≥3)만.
트래커 '차기주자 성·연령별' 뷰(renderCandidatePref 재사용, 후보별 묶음·정당색)가 소비.
"""
from __future__ import annotations
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGES = ["18-29", "30", "40", "50", "60", "70+"]
SEXES = ["남성", "여성"]


def load_meta():
    meta = {}
    for f in sorted(glob.glob(str(ROOT / "data/polls/aggregated*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for p in d.get("polls", []):
            nid = str(p.get("ntt_id"))
            date = p.get("period_end") or p.get("date")
            if nid and nid not in meta and date:
                meta[nid] = (date, p.get("agency"), p.get("sido") or "")
    return meta


def clean_row(row):
    """실제 후보(party 있음)만. 다자(≥3) 아니면 폐기 — 양자·소수표 제외."""
    cand = [c for c in (row or []) if c.get("party")]
    return cand if len(cand) >= 3 else None


def build():
    cd = json.load(open(ROOT / "data/raw/parsed/cand_demographics.json", encoding="utf-8"))
    meta = load_meta()
    groups: dict[str, list] = {}
    agencies, dropped_region, unmapped, bad = set(), 0, 0, 0

    def push(key, date, agency, row):
        nonlocal bad
        row = clean_row(row)
        if not row:
            bad += 1
            return
        groups.setdefault(key, []).append({"date": date, "agency": agency, "c": row})
        if agency:
            agencies.add(agency)

    for ntt, v in cd.items():
        m = meta.get(str(ntt))
        if not m:
            unmapped += 1
            continue
        date, agency, sido = m
        if sido and sido not in ("", "전국"):
            dropped_region += 1
            continue
        for s, row in (v.get("성별") or {}).items():
            if s in SEXES and row:
                push(f"성별|{s}", date, agency, row)
        for a, row in (v.get("연령") or {}).items():
            if a in AGES and row:
                push(f"연령|{a}", date, agency, row)
        for s, ages in (v.get("성연령") or {}).items():
            for a, row in (ages or {}).items():
                if s in SEXES and a in AGES and row:
                    push(f"{s}|{a}", date, agency, row)

    for k in groups:
        groups[k].sort(key=lambda x: x["date"])
    npts = sum(len(v) for v in groups.values())
    out = {
        "_meta": {"kind": "cand_demographics_trend",
                  "agencies": sorted(a for a in agencies if a),
                  "n_polls": len(cd), "n_mapped": len(cd) - unmapped - dropped_region,
                  "note": "차기주자(후보지지) 성×연령 상시 추이(전 회차 union, 전국, 다자≥3). "
                          "선거 비종속 — 트래커 소비."},
        "groups": groups,
    }
    dst = ROOT / "data/polls/cand_demographics_trend.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {dst.name}: 그룹 {len(groups)}개, 총 {npts}점, 기관 {len(out['_meta']['agencies'])}곳")
    print(f"  매핑 {out['_meta']['n_mapped']}/{len(cd)} (미매핑 {unmapped}·지역제외 {dropped_region}·비다자 {bad})")
    for key in ("연령|18-29", "성별|남성"):
        s = groups.get(key, [])
        if s:
            last = s[-1]
            top = sorted([c for c in last["c"]], key=lambda c: -c["pct"])[:4]
            print(f"  {key}: {len(s)}점 {s[0]['date']}~{s[-1]['date']} | 끝 {last['date']}: "
                  + ", ".join(f"{c['name']} {c['pct']}" for c in top))


if __name__ == "__main__":
    build()
