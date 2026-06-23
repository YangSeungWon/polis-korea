#!/usr/bin/env python3
"""정당지지 성×연령 '상시 추이' served 데이터 — 선거 비종속 연속 시계열.

입력:
  data/raw/parsed/party_demographics.json   (extract_party_demographics, ntt→성연령 정당지지)
  data/polls/aggregated_*.json (union)        (ntt→period_end, agency, sido) — 날짜·기관·전국여부
출력:
  data/polls/party_demographics_trend.json
    { _meta, groups: { "성별|남성": [{date, agency, c:[{name,party,pct}]}], "연령|30":[...],
                       "남성|18-29":[...] } }

후보지지 추이(build_poll_demographics)의 정당 버전 + 선거 비종속(전 회차 union). 전국만.
트래커의 정당지지 성·연령별 추이 뷰가 소비.
"""
from __future__ import annotations
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGES = ["18-29", "30", "40", "50", "60", "70+"]
SEXES = ["남성", "여성"]
# 무당·유보 계열 특수열 — 부분문자열로 흡수(잘모름·지지정당없음·모름/무응답 등 변종 다수).
_SPECIAL_RE = re.compile(r"없음|모름|무응답|유보|기타|무당|부동|중도층|응답안|태도")

_PARTIES = None


def clean_row(row):
    """모든 열이 registry 정당 또는 무당/유보 특수여야 통과. 깨진 정당명(헤더분해 실패·
    후보표 누수, 예 '다음중혁신당이준석')이 하나라도 있으면 행 폐기."""
    global _PARTIES
    if _PARTIES is None:
        reg = json.load(open(ROOT / "data/parties/registry.json", encoding="utf-8"))["parties"]
        # 동음이의 분리키(국민의당(2016)·민주국민당(2000) 등)는 평문 base명도 유효로.
        _PARTIES = set(reg) | {re.sub(r"\(\d{4}\)$", "", k) for k in reg}
    if not row:
        return None
    for c in row:
        nm = c["name"]
        if nm not in _PARTIES and not _SPECIAL_RE.search(nm):
            return None
    return row


def load_meta():
    """전 aggregated_*.json union → {ntt: (period_end, agency, sido)}. 첫 등장 우선."""
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


def build():
    pd = json.load(open(ROOT / "data/raw/parsed/party_demographics.json", encoding="utf-8"))
    meta = load_meta()

    groups: dict[str, list] = {}
    agencies, dropped_region, unmapped = set(), 0, 0

    bad_rows = 0

    def push(key, date, agency, row):
        nonlocal bad_rows
        row = clean_row(row)
        if not row:
            bad_rows += 1
            return
        groups.setdefault(key, []).append({"date": date, "agency": agency, "c": row})
        if agency:
            agencies.add(agency)

    for ntt, v in pd.items():
        m = meta.get(str(ntt))
        if not m:
            unmapped += 1
            continue
        date, agency, sido = m
        if sido and sido not in ("", "전국"):     # 전국 정당지지만 — 지역 폴 제외
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
        "_meta": {"kind": "party_demographics_trend",
                  "agencies": sorted(a for a in agencies if a),
                  "n_polls": len(pd), "n_mapped": len(pd) - unmapped - dropped_region,
                  "note": "정당지지 성×연령 상시 추이(전 회차 union, 전국). 단일선택 합≈100 검증분만. "
                          "선거 비종속 — 트래커 소비."},
        "groups": groups,
    }
    dst = ROOT / "data/polls/party_demographics_trend.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {dst.name}: 그룹 {len(groups)}개, 총 {npts}점, 기관 {len(out['_meta']['agencies'])}곳")
    print(f"  매핑 {out['_meta']['n_mapped']}/{len(pd)} (미매핑 {unmapped}·지역제외 {dropped_region})")
    for key in ("연령|18-29", "연령|60", "성별|남성", "남성|18-29"):
        s = groups.get(key, [])
        if s:
            last = s[-1]
            top = sorted(last["c"], key=lambda c: -c["pct"])[:3]
            print(f"  {key}: {len(s)}점 {s[0]['date']}~{s[-1]['date']} | 끝 {last['date']}: "
                  + ", ".join(f"{c['name']} {c['pct']}" for c in top))


if __name__ == "__main__":
    build()
