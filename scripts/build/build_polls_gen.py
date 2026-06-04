"""국회의원선거(총선) 여론조사 build — nesdc_<id>_polls.csv + parsed/*.json → aggregated_<id>.json.

build_polls_pres.py(대선) 골격 재사용. 총선은 race 단위가 **선거구(254개)**라 대선과 또 다르다:
  - 지역구 후보지지: 선거구별 후보 race. 고정 roster 불가(~700 후보) → NEC 선거구별 명부
    (nec_roster_22gen.json)로 anchor. parsed 후보명이 그 선거구 roster에 있으면 채택.
    (여론조사꽃류 괘선없는 cross-tab은 컬럼 병합으로 후보명이 깨져 roster 미매칭 → 자연 탈락.
     별도 추출기는 후속 과제. docs/multi-kind-build-polls.md)
  - 비례 정당투표: 전국 정당 race. roster.proportional_parties(38개)로 anchor.
  - 정당지지: 일반 정당 지지(민주+국힘) — 부가 metric.

NESDC region("부산광역시 부산진구 갑 선거구")을 정규화해 선거구 key("부산광역시|부산진구갑")로
roster 매칭. 중복 토큰·압축 갑을·오타(서울틀별시) 보정 포함.

법적 의무는 지선/대선 build와 동일 (의뢰자·기관·기간·표본·응답률·표본오차 + source_url).
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "build"))
# 지선 build 순수 helper 재사용 (side-effect: 9회 roster load — 미사용, 무해)
from build_polls import (  # noqa: E402
    SIDO_CANONICAL, canon_sido, parse_survey_period, to_float, is_self_poll,
)

ELECTION_DATE = date(2024, 4, 10)
ROSTER_PATH = ROOT / "data" / "raw" / "nec_roster_22gen.json"

SIDO_SHORT = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}
_SIDO_VALUES = set(SIDO_CANONICAL.values()) | set(SIDO_SHORT.values())

# horse-race가 아닌 문항 reject (적합도·가상·단일화·정책·성향 류)
REJECT_TITLE = re.compile(
    r"적합|경선|가상|단일화|단일\s*후보|찍고\s*싶지|절대|비호감|호감도|역선택|"
    r"성향|국정|평가|만족|정책|현안|\bvs\b|\bVS\b"
)
PROP_BIG = {"더불어민주연합", "국민의미래"}   # 비례 양대 위성정당
PARTY_BIG = {"더불어민주당", "국민의힘"}      # 정당지지 양대정당


def load_roster() -> tuple[dict, set]:
    d = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    return d["districts"], set(d["proportional_parties"])


def load_meta(csv_path: Path) -> dict[str, dict]:
    if not csv_path.exists():
        return {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {row["ntt_id"]: row for row in csv.DictReader(f)}


def load_parsed(parsed_dir: Path, ids: set[str]) -> dict[str, dict]:
    """ntt_id → parsed JSON (후보/정당 문항 풍부한 쪽)."""
    by_id: dict[str, dict] = {}

    def score(jd):
        return sum(1 for q in jd.get("questions", [])
                   if q.get("candidates") and any("pct" in c for c in q["candidates"]))

    for path in parsed_dir.glob("*.json"):
        nid = path.name.split("_", 1)[0]
        if nid not in ids:
            continue
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        nid = str(d.get("ntt_id", nid))
        if nid not in by_id or score(d) > score(by_id[nid]):
            by_id[nid] = d
    return by_id


def district_index(districts: dict) -> dict:
    """{sido: [(base, suffix, fullname)]} — base 길이 desc 정렬 (긴 매칭 우선)."""
    idx: dict[str, list] = defaultdict(list)
    for key in districts:
        sido, _, name = key.partition("|")
        m = re.match(r"^(.*?)([갑을병정])$", name)
        base, suf = (m.group(1), m.group(2)) if m else (name, "")
        idx[sido].append((base, suf, name))
    for sido in idx:
        idx[sido].sort(key=lambda x: -len(x[0]))
    return idx


def region_to_district(region: str, idx: dict | None = None) -> tuple[str, str]:
    """NESDC region → (sido_canonical, 선거구). roster index로 매칭.

    region 텍스트가 지저분함(괄호 갑을병 "평택시(병)", 비연속/전체명 중복
    "춘천시…양구군춘천시…양구군을", 구분자 "·"). 정제 후 roster 선거구명(base)이 region에
    포함되고 갑을병 suffix가 맞는 것 중 가장 긴 base를 채택. idx 없으면 휴리스틱 결합 fallback.
    """
    if not region or region.startswith("전국"):
        return ("", "")
    region = region.replace("서울틀별시", "서울특별시")
    region = re.sub(r"[()·,]", " ", region)
    toks = [t for t in region.split() if t not in ("선거구", "전체", "전지역", "전 지역")]
    if not toks:
        return ("", "")
    sido = SIDO_SHORT.get(toks[0], canon_sido(toks[0]))
    suffix = ""
    parts: list[str] = []
    for t in toks[1:]:
        if SIDO_SHORT.get(t, canon_sido(t)) in _SIDO_VALUES:  # 반복 시도 제거
            continue
        if t in ("갑", "을", "병", "정"):
            suffix = t
            continue
        m = re.match(r"^(.+?)([갑을병정])$", t)  # 토큰 끝 갑을병 분리
        if m:
            parts.append(m.group(1))
            suffix = m.group(2)
            continue
        parts.append(t)
    joined = "".join(parts)
    if idx is not None:
        for base, suf, name in idx.get(sido, []):
            if base and base in joined and (suf == suffix or not suffix):
                return (sido, name)
    return (sido, joined + suffix)


def normalize_pcts(cands: list[dict]) -> bool:
    pcts = [c.get("pct") for c in cands if c.get("pct") is not None]
    if not pcts:
        return False
    s = sum(pcts)
    if 700 <= s <= 1100:  # 0.1% 단위
        for c in cands:
            if c.get("pct") is not None:
                c["pct"] = round(c["pct"] / 10, 1)
        s /= 10
    return not (s == 0 or s > 110 or s < 30)


def accept_district_race(q: dict, roster_dist: dict[str, str]) -> list[dict] | None:
    """지역구 후보 race면 정제 candidates 반환. roster_dist 후보명으로 anchor."""
    if not roster_dist or REJECT_TITLE.search(q.get("title", "")):
        return None
    keep = [c for c in (q.get("candidates") or [])
            if c.get("name", "") in roster_dist and c.get("pct") is not None]
    if len(keep) < 2:
        return None
    if not normalize_pcts(keep):
        return None
    return [{"name": c["name"], "party": c.get("party") or roster_dist[c["name"]],
             "pct": c["pct"]} for c in keep]


def accept_prop_race(q: dict, prop: set) -> list[dict] | None:
    """비례 정당투표면 정제 candidates(party-only) 반환. proportional_parties anchor.

    폴은 위성정당(더불어민주연합·국민의미래) 대신 모정당명(더불어민주당·국민의힘)으로 묻기도
    해서 anchor에 모정당명도 포함. 양대(민주계+국힘계)가 둘 다 있어야 의미 있는 비례 race.
    """
    anchor = prop | {"더불어민주당", "국민의힘"}
    keep = []
    for c in (q.get("candidates") or []):
        party = (c.get("party") or c.get("name") or "").strip()
        if party in anchor and c.get("pct") is not None:
            keep.append({"name": "", "party": party, "pct": c["pct"]})
    parties = {c["party"] for c in keep}
    has_dem = "더불어민주연합" in parties or "더불어민주당" in parties
    has_ppp = "국민의미래" in parties or "국민의힘" in parties
    if not (has_dem and has_ppp) or len(keep) < 3:
        return None
    if not normalize_pcts(keep):
        return None
    return keep


def accept_party_race(q: dict) -> list[dict] | None:
    """일반 정당지지면 정제 candidates 반환."""
    keep = [{"name": "", "party": c["party"], "pct": c["pct"]}
            for c in (q.get("candidates") or [])
            if c.get("party") and c.get("pct") is not None]
    if not (PARTY_BIG <= {c["party"] for c in keep}):
        return None
    if re.search(r"비례", q.get("title", "")):  # 비례는 accept_prop_race가 처리
        return None
    if not normalize_pcts(keep):
        return None
    return keep


def build(csv_path: Path, parsed_dir: Path) -> dict:
    districts, prop = load_roster()
    didx = district_index(districts)
    meta = load_meta(csv_path)
    parsed = load_parsed(parsed_dir, set(meta))

    polls = []
    skipped_no_pdf = skipped_no_race = 0

    for ntt_id, m in meta.items():
        p = parsed.get(ntt_id)
        if not p:
            skipped_no_pdf += 1
            continue
        sido, district = region_to_district(m.get("region", ""), didx)
        roster_dist = districts.get(f"{sido}|{district}", {}) if district else {}
        ps = m.get("survey_start", "") or parse_survey_period(m.get("survey_period", ""))[0]
        pe = m.get("survey_end", "") or parse_survey_period(m.get("survey_period", ""))[1]
        if ps and pe and ps > pe:
            ps, pe = pe, ps
        requester = m.get("requester", "")
        self_poll = is_self_poll(requester)

        def emit(metric, office_level, cands, title, tno):
            polls.append({
                "ntt_id": ntt_id,
                "source_url": m.get("source_url", ""),
                "agency": m.get("agency", ""),
                "co_agency": m.get("co_agency", ""),
                "requester": requester,
                "is_self_poll": self_poll,
                "method": m.get("method", ""),
                "sample_size": to_float(m.get("sample_size", "")),
                "response_rate": to_float(m.get("response_rate", "")),
                "contact_rate": to_float(m.get("contact_rate", "")),
                "sample_error": m.get("sample_error", ""),
                "period_start": ps,
                "period_end": pe,
                "reg_date": m.get("reg_date", ""),
                "sido": sido,
                "sigungu": "",
                "district": district if metric == "후보지지" else "",
                "office_level": office_level,
                "office_label": office_level,
                "metric_type": metric,
                "table_no": tno,
                "table_title": title,
                "candidates": cands,
            })

        any_emitted = False
        for q in p.get("questions", []):
            eo = q.get("election_office", "")
            title, tno = q.get("title", ""), q.get("table_no", "")
            if eo == "비례정당":
                c = accept_prop_race(q, prop)
                if c:
                    emit("비례대표", "비례대표", c, title, tno); any_emitted = True
            elif eo == "정당지지":
                c = accept_party_race(q)
                if c:
                    emit("정당지지", "정당지지", c, title, tno); any_emitted = True
            elif eo == "후보지지":
                c = accept_district_race(q, roster_dist)
                if c:
                    emit("후보지지", "국회의원", c, title, tno); any_emitted = True
        if not any_emitted:
            skipped_no_race += 1

    polls = postprocess(polls)

    now = datetime.now()
    return {
        "_meta": {
            "generated_at": now.isoformat(timespec="seconds"),
            "election": "22nd-general-2024",
            "election_date": ELECTION_DATE.isoformat(),
            "source": "NESDC 등록현황 (nesdc.go.kr)",
            "legal_notice": "본 자료는 NESDC 등록 조사 인용. 인용 시 의뢰자·기관·조사기간·표본수·응답률·표본오차 표시 의무.",
            "stats": {
                "total_polls_meta": len(meta),
                "matched_parsed": sum(1 for x in meta if x in parsed),
                "emitted_records": len(polls),
                "skipped_no_pdf": skipped_no_pdf,
                "skipped_no_race": skipped_no_race,
            },
        },
        "polls": polls,
    }


def _sum(p):
    return sum(c.get("pct") or 0 for c in p["candidates"] if c.get("pct") is not None)


def postprocess(polls: list[dict]) -> list[dict]:
    """record 내 dedup → split 표 merge → 카드 dedup(ntt,metric,sido,district)."""
    for p in polls:
        seen = {}
        for c in p["candidates"]:
            k = c.get("name") or c.get("party")
            if k and (k not in seen or (c.get("pct") or 0) > (seen[k].get("pct") or 0)):
                seen[k] = c
        p["candidates"] = list(seen.values())

    # 같은 (ntt, metric, sido, district, title) split 표 — pct 일치 시 merge
    groups = defaultdict(list)
    for p in polls:
        groups[(p["ntt_id"], p["metric_type"], p["sido"], p["district"], p["table_title"])].append(p)
    merged = []
    for ps in groups.values():
        clusters = []
        for p in ps:
            pm = {(c.get("name") or c.get("party")): c.get("pct") for c in p["candidates"]
                  if (c.get("name") or c.get("party")) and c.get("pct") is not None}
            for cl in clusters:
                shared = set(cl["pm"]) & set(pm)
                if shared and all(abs((cl["pm"][k] or 0) - (pm[k] or 0)) <= 1.0 for k in shared):
                    base = cl["rec"]
                    acc = {(c.get("name") or c.get("party")): c for c in base["candidates"]}
                    for c in p["candidates"]:
                        k = c.get("name") or c.get("party")
                        if k and (k not in acc or (c.get("pct") or 0) > (acc[k].get("pct") or 0)):
                            acc[k] = c
                    base["candidates"] = list(acc.values())
                    cl["pm"].update(pm)
                    break
            else:
                clusters.append({"pm": pm, "rec": p})
        merged.extend(cl["rec"] for cl in clusters)
    polls = merged

    # 한 (ntt, metric, sido, district) = 한 race. 후보 최다 → 표본 큰 카드.
    seen_card = {}
    out = []
    for p in polls:
        k = (p["ntt_id"], p["metric_type"], p["sido"], p["district"])
        sc = (len(p["candidates"]), p.get("sample_size") or 0)
        if k not in seen_card:
            seen_card[k] = len(out)
            out.append(p)
        elif sc > (len(out[seen_card[k]]["candidates"]), out[seen_card[k]].get("sample_size") or 0):
            out[seen_card[k]] = p
    return out


def main():
    ap = argparse.ArgumentParser(description="총선 여론조사 aggregated.json build")
    ap.add_argument("--csv", default="data/raw/nesdc_22gen_polls.csv")
    ap.add_argument("--parsed", default="data/raw/parsed")
    ap.add_argument("--out", default="data/polls/aggregated_22nd.json")
    args = ap.parse_args()
    csv_path = Path(args.csv) if Path(args.csv).is_absolute() else ROOT / args.csv
    parsed_dir = Path(args.parsed) if Path(args.parsed).is_absolute() else ROOT / args.parsed
    out_path = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out

    out = build(csv_path, parsed_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    st = out["_meta"]["stats"]
    bym = Counter(p["metric_type"] for p in out["polls"])
    nd = len({p["district"] for p in out["polls"] if p["district"]})
    print(f"메타 {st['total_polls_meta']}, 매칭 {st['matched_parsed']}, "
          f"emit {st['emitted_records']} {dict(bym)} | 지역구 {nd}개", file=sys.stderr)
    print(f"  skip(PDF없음) {st['skipped_no_pdf']}, skip(race없음) {st['skipped_no_race']}", file=sys.stderr)
    print(f"→ {out_path.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
