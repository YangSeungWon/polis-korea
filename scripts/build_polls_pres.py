"""대통령선거 여론조사 build — nesdc_<id>_polls.csv + parsed/*.json → aggregated_<id>.json.

build_polls.py(지선)와 분리된 대선 전용 path. 지선 build는 광역/기초/교육감 office 분류와
그에 딸린 ~700줄 후처리(단일정당 경선·양자대결·column-bleed 등)가 핵심인데, 대선은 구조가
근본적으로 다르다:

  - race가 단 하나 (대통령). office 분류 불필요.
  - scope는 전국(national) 또는 시도 cross-tab. 시군구 단위 무의미.
  - 후보군이 시간에 따라 변함 (경선 → 단일화 → 본선 5인). 따라서 "고정 후보 list"가 아니라
    "대선 주자 roster"로 horse-race 문항을 anchor하고, 적합도·양자·단일화·가상대결 같은
    비(非)헤드라인 시나리오를 reject한다.

남기는 metric:
  - 후보지지 (다자대결 horse-race): roster 후보 3+ 등장 + 이재명 포함 + 합 정상.
  - 정당지지 (nationwide/시도): 민주+국힘 동시 등장.

총선 build(build_polls_gen.py)도 같은 skeleton 재사용 예정 — roster/accept 규칙만 교체.
참고: docs/multi-kind-build-polls.md.

법적 의무 (지선 build와 동일): 각 레코드에 의뢰자·기관·조사기간·표본수·응답률·표본오차 +
source_url 보존, 의뢰자가 정당·후보 본인이면 is_self_poll 표시.
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
# 지선 build의 순수 helper 재사용 (side-effect: 9회 roster load — 미사용, 무해)
from build_polls import (  # noqa: E402
    SIDO_CANONICAL, canon_sido, parse_survey_period, to_float, is_self_poll,
)

# ── 21대 대선 설정 ──────────────────────────────────────────────────────────
ELECTION_DATE = date(2025, 6, 3)
BLACKOUT_START = date(2025, 5, 28)        # 6일 전 0시부터 공표 금지
BLACKOUT_END = datetime(2025, 6, 3, 18, 0)  # 투표 마감 18시 해제
# 21대 대선은 윤석열 탄핵(2024-12-03 비상계엄 → 2025-04-04 파면)으로 치러진 보궐성 대선.
# NESDC가 "제21대 대통령선거" gubun으로 등록한 데엔 그 이전의 정례 "차기 대선주자/정당지지"
# 사운딩(2022~2024 봄 — 사실상 22대 총선기 조사)도 섞여 timeline을 오염시킨다. 계엄 사태로
# 이 선거가 사실상 점화된 2024-12-03을 campaign window 하한으로 잡아 그 이전 조사는 제외.
CAMPAIGN_START = date(2024, 12, 3)
# 본선 후보 5인 + 경선 국면 가상 ballot도 6인 안팎. 7인+ 다후보 표는 단일선택 ballot이 아니라
# "차기주자 선호도/적합도" 매트릭스라 horse-race에서 제외.
MAX_BALLOT = 6

# 대선 주자 roster — 최종 5인 + 경선·단일화 국면에 horse-race 문항에 실제 등장한 주요 주자.
# 이 set으로 후보 race를 anchor(OCR 잡음·정책응답·성향응답 제거)하고 정당 backfill에 사용.
# party는 조사 시점 소속/계열 기준 (parsed에 party 없을 때만 적용).
ROSTER: dict[str, str] = {
    # 최종 본선 5인 (data/results/presidential_21.json)
    "이재명": "더불어민주당",
    "김문수": "국민의힘",
    "이준석": "개혁신당",
    "권영국": "민주노동당",
    "송진호": "무소속",
    # 경선·단일화 국면 주요 주자 (본선 전 다자/가상대결에 등장)
    "한덕수": "무소속",
    "홍준표": "국민의힘",
    "한동훈": "국민의힘",
    "안철수": "국민의힘",
    "오세훈": "국민의힘",
    "나경원": "국민의힘",
    "유승민": "국민의힘",
    "황교안": "국민의힘",
    "김동연": "더불어민주당",
    "김경수": "더불어민주당",
    "김부겸": "더불어민주당",
    "이낙연": "새로운미래",
}

# horse-race가 아닌 문항 reject (후보 이름이 섞여 있어도 헤드라인 지지율 아님).
# 적합도/경선 = 같은 당 주자 비교, 양자 = 2자 가상, 단일화 = 시나리오, 가상대결 = pre-nomination,
# 나머지는 비호감/역선택/정책/성향 류.
REJECT_TITLE = re.compile(
    r"적합|경선|양자|단일화|단일\s*후보|가상\s*대결|맞대결|찍고\s*싶지|절대|"
    r"비호감|호감도|역선택|위험|성향|개헌|권력\s*구조|책임|증세|과세|종부세|면세|"
    r"실수|잘못|당선\s*가능|인지도|만약|\bvs\b|\bVS\b"
)
# 정당지지 양대정당 (둘 다 있어야 의미 있는 race)
PARTY_BIG = {"더불어민주당", "국민의힘"}


def load_meta(csv_path: Path) -> dict[str, dict]:
    if not csv_path.exists():
        return {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {row["ntt_id"]: row for row in csv.DictReader(f)}


def load_parsed(parsed_dir: Path, ids: set[str]) -> dict[str, dict]:
    """ntt_id → parsed PDF JSON. 한 ntt_id에 여러 PDF면 후보지지/정당지지 문항 많은 쪽."""
    by_id: dict[str, dict] = {}

    def score(jd):
        return sum(
            1 for q in jd.get("questions", [])
            if q.get("candidates") and any("pct" in c for c in q["candidates"])
        )

    for path in parsed_dir.glob("*.json"):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        nid = str(d.get("ntt_id", ""))
        if not nid or nid not in ids:
            continue
        if nid not in by_id or score(d) > score(by_id[nid]):
            by_id[nid] = d
    return by_id


def pres_sido(region: str) -> str:
    """대선 region → 시도 canonical (전국·복합·해석불가 → "" = nationwide).

    "전국 전체" → ""(national). "충청북도 전체" → "충청북도".
    "대구광역시 전체 경상북도 전체"(복합 권역) → "" — 단일 시도 cross-tab 아님.
    """
    if not region or region.startswith("전국"):
        return ""
    toks = [canon_sido(t) for t in region.split() if t not in ("전체", "전지역", "전 지역")]
    sidos = {t for t in toks if t in SIDO_CANONICAL.values()}
    return next(iter(sidos)) if len(sidos) == 1 else ""


def normalize_pcts(cands: list[dict]) -> bool:
    """pct 스케일 보정 + 합 sanity. 유효하면 True, 폐기 대상이면 False."""
    pcts = [c.get("pct") for c in cands if c.get("pct") is not None]
    if not pcts:
        return False
    s = sum(pcts)
    if 700 <= s <= 1100:  # 0.1% 단위 (합 ~1000) → /10
        for c in cands:
            if c.get("pct") is not None:
                c["pct"] = round(c["pct"] / 10, 1)
        s /= 10
    if s == 0 or s > 110 or s < 30:  # 추출 실패·일부만 추출
        return False
    return True


def accept_candidate_race(q: dict) -> list[dict] | None:
    """후보지지 horse-race면 정제된 candidates 반환, 아니면 None."""
    title = q.get("title", "")
    if REJECT_TITLE.search(title):
        return None
    cands = q.get("candidates") or []
    # roster 후보만 남김 — OCR 잡음(더민/불어주당)·정책응답(보수/진보)·기호 제거
    keep = [c for c in cands
            if c.get("name", "") in ROSTER and c.get("pct") is not None]
    if not (3 <= len(keep) <= MAX_BALLOT) or not any(c["name"] == "이재명" for c in keep):
        return None
    if not normalize_pcts(keep):
        return None
    return [{"name": c["name"], "party": c.get("party") or ROSTER[c["name"]],
             "pct": c["pct"]} for c in keep]


def accept_party_race(q: dict) -> list[dict] | None:
    """정당지지면 정제된 candidates(party-only) 반환, 아니면 None."""
    cands = [c for c in (q.get("candidates") or [])
             if c.get("party") and c.get("pct") is not None]
    parties = {c["party"] for c in cands}
    if not (PARTY_BIG <= parties):
        return None
    if re.search(r"경선|단일화|당내", q.get("title", "")):
        return None
    if not normalize_pcts(cands):
        return None
    return [{"name": "", "party": c["party"], "pct": c["pct"]} for c in cands]


def build(csv_path: Path, parsed_dir: Path) -> dict:
    meta = load_meta(csv_path)
    parsed = load_parsed(parsed_dir, set(meta))

    polls = []
    skipped_no_pdf = 0
    skipped_no_race = 0
    skipped_pre_campaign = 0

    for ntt_id, m in meta.items():
        p = parsed.get(ntt_id)
        if not p:
            skipped_no_pdf += 1
            continue
        sido = pres_sido(m.get("region", ""))
        period_start = m.get("survey_start", "") or parse_survey_period(m.get("survey_period", ""))[0]
        period_end = m.get("survey_end", "") or parse_survey_period(m.get("survey_period", ""))[1]
        if period_start and period_end and period_start > period_end:
            period_start, period_end = period_end, period_start
        # campaign window 하한 — 계엄 사태 이전의 정례 사운딩 제외
        if period_end and period_end < CAMPAIGN_START.isoformat():
            skipped_pre_campaign += 1
            continue
        requester = m.get("requester", "")
        self_poll = is_self_poll(requester)

        def emit(metric, office_level, cands, title, table_no):
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
                "period_start": period_start,
                "period_end": period_end,
                "reg_date": m.get("reg_date", ""),
                "sido": sido,
                "sigungu": "",
                "office_level": office_level,
                "office_label": office_level,
                "metric_type": metric,
                "table_no": table_no,
                "table_title": title,
                "candidates": cands,
            })

        any_emitted = False
        for q in p.get("questions", []):
            eo = q.get("election_office", "")
            title = q.get("title", "")
            tno = q.get("table_no", "")
            if eo == "정당지지":
                cands = accept_party_race(q)
                if cands:
                    emit("정당지지", "정당지지", cands, title, tno)
                    any_emitted = True
            else:
                cands = accept_candidate_race(q)
                if cands:
                    emit("후보지지", "대통령", cands, title, tno)
                    any_emitted = True
        if not any_emitted:
            skipped_no_race += 1

    polls = postprocess(polls)

    now = datetime.now()
    blackout_active = BLACKOUT_START <= now.date() <= BLACKOUT_END.date()
    if blackout_active and now.date() == BLACKOUT_END.date() and now.hour >= 18:
        blackout_active = False

    return {
        "_meta": {
            "generated_at": now.isoformat(timespec="seconds"),
            "election": "21st-pres-2025",
            "election_date": ELECTION_DATE.isoformat(),
            "blackout_start": BLACKOUT_START.isoformat(),
            "blackout_end": BLACKOUT_END.isoformat(timespec="minutes"),
            "blackout_active": blackout_active,
            "source": "NESDC 등록현황 (nesdc.go.kr)",
            "legal_notice": "본 자료는 NESDC 등록 조사 인용. 인용 시 의뢰자·기관·조사기간·표본수·응답률·표본오차 표시 의무.",
            "stats": {
                "total_polls_meta": len(meta),
                "matched_parsed": sum(1 for m in meta if m in parsed),
                "emitted_records": len(polls),
                "skipped_no_pdf": skipped_no_pdf,
                "skipped_no_race": skipped_no_race,
                "skipped_pre_campaign": skipped_pre_campaign,
            },
        },
        "polls": polls,
    }


def _sum(p: dict) -> float:
    return sum(c.get("pct") or 0 for c in p["candidates"] if c.get("pct") is not None)


def postprocess(polls: list[dict]) -> list[dict]:
    """record 내 dedup → pct-일치 split 표만 merge → 카드 dedup → 최종 sanity."""
    # 1) record 내 동일 후보/정당 dedup (pct 큰 쪽)
    for p in polls:
        seen: dict[str, dict] = {}
        for c in p["candidates"]:
            key = c.get("name") or c.get("party")
            if not key:
                continue
            if key not in seen or (c.get("pct") or 0) > (seen[key].get("pct") or 0):
                seen[key] = c
        p["candidates"] = list(seen.values())

    # 2) 같은 (ntt, metric, sido, table_title) 안에서 — 공유 후보의 pct가 일치할 때만 merge
    #    (진짜 한 표가 두 row로 split된 경우). pct가 다르면 다른 시나리오(다자 vs 단일화 등)라
    #    합치면 합 100 초과 garble → 별도 record로 두고 아래 카드 dedup이 하나만 남긴다.
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in polls:
        groups[(p["ntt_id"], p["metric_type"], p["sido"], p["table_title"])].append(p)
    merged = []
    for ps in groups.values():
        clusters: list[dict] = []
        for p in ps:
            pm = {(c.get("name") or c.get("party")): c.get("pct") for c in p["candidates"]
                  if (c.get("name") or c.get("party")) and c.get("pct") is not None}
            for cl in clusters:
                shared = set(cl["pm"]) & set(pm)
                if shared and all(abs((cl["pm"][k] or 0) - (pm[k] or 0)) <= 1.0 for k in shared):
                    base = cl["rec"]
                    acc = {(c.get("name") or c.get("party")): c for c in base["candidates"]}
                    for c in p["candidates"]:
                        key = c.get("name") or c.get("party")
                        if key and (key not in acc or (c.get("pct") or 0) > (acc[key].get("pct") or 0)):
                            acc[key] = c
                    base["candidates"] = list(acc.values())
                    cl["pm"].update(pm)
                    break
            else:
                clusters.append({"pm": pm, "rec": p})
        merged.extend(cl["rec"] for cl in clusters)
    polls = merged

    # 3) 한 등록(ntt)·metric·sido = 한 race. 후보지지는 '다자' 명시 → 합 100 근접 → 표본 큰 것;
    #    정당지지는 표본 큰 것. (가상·단일화 sub-scenario 잔여를 본선 다자가 이기게)
    def score(p):
        if p["metric_type"] == "후보지지":
            return ("다자" in p["table_title"], -abs(_sum(p) - 100), p.get("sample_size") or 0)
        return (True, 0, p.get("sample_size") or 0)
    seen_card: dict[tuple, int] = {}
    deduped: list[dict] = []
    for p in polls:
        k = (p["ntt_id"], p["metric_type"], p["sido"])
        if k not in seen_card:
            seen_card[k] = len(deduped)
            deduped.append(p)
        elif score(p) > score(deduped[seen_card[k]]):
            deduped[seen_card[k]] = p

    # 4) 최종 sanity — merge·dedup 후에도 후보지지 합이 [40,110] 벗어나거나 ballot 크기 초과면
    #    시나리오 혼입·매트릭스라 drop.
    out = []
    for p in deduped:
        if p["metric_type"] == "후보지지":
            n = len(p["candidates"])
            if not (3 <= n <= MAX_BALLOT) or not (40 <= _sum(p) <= 110):
                continue
            # 후보 전원이 한 정당이면 본선 ballot이 아니라 당내 경선/선호도
            # ("더불어민주당 차기 대선 후보", "범진보 주자 선호도" 등) → drop.
            if len({c["party"] for c in p["candidates"]}) < 2:
                continue
        out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description="대선 여론조사 aggregated.json build")
    ap.add_argument("--csv", default="data/raw/nesdc_21pres_polls.csv",
                    help="NESDC 메타 CSV path")
    ap.add_argument("--parsed", default="data/raw/parsed", help="parsed JSON 디렉터리")
    ap.add_argument("--out", default="data/polls/aggregated_21pres.json", help="출력 JSON path")
    args = ap.parse_args()

    csv_path = Path(args.csv) if Path(args.csv).is_absolute() else ROOT / args.csv
    parsed_dir = Path(args.parsed) if Path(args.parsed).is_absolute() else ROOT / args.parsed
    out_path = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out

    out = build(csv_path, parsed_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    st = out["_meta"]["stats"]
    by_metric = Counter(p["metric_type"] for p in out["polls"])
    print(f"메타 {st['total_polls_meta']}건, 파싱 매칭 {st['matched_parsed']}건, "
          f"emit {st['emitted_records']}개 {dict(by_metric)}", file=sys.stderr)
    print(f"  skip(PDF없음) {st['skipped_no_pdf']}, skip(race없음) {st['skipped_no_race']}",
          file=sys.stderr)
    print(f"→ {out_path.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
