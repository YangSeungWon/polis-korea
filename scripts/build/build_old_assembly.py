"""제헌~12대(1948~1985) 총선 — report.xhtml 수집분(data/raw/lod/report_*.json)으로
results/{id}.json + elections/{id}.json(아카이브 등록) 생성.

당선인명부 = 당선자만 → 선거구별 won 후보(소선거구 1명·중선거구 9~12대 2명).
전국구/유정회(6~12대)는 별도 투입(JEON) — 없는 회차/미투입은 지역구만(dist mode·정직).
제헌~5대는 전국구 없어 지역구만으로 완전(5대는 민의원, 참의원 별도·미수록).

사용: python scripts/build/build_old_assembly.py   (이후 sync_archive_html.py 실행)
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "lod"
RESULTS = ROOT / "data" / "results"
ELECTIONS = ROOT / "data" / "elections"

# n → (id slug, 선거일, 비고). 13대~는 별도(이미 있음).
ROUNDS = {
    1: ("1st-general-1948", "1948-05-10", "제헌국회 — 무소속 다수"),
    2: ("2nd-general-1950", "1950-05-30", "한국전쟁 직전"),
    3: ("3rd-general-1954", "1954-05-20", ""),
    4: ("4th-general-1958", "1958-05-02", ""),
    5: ("5th-general-1960", "1960-07-29", "4·19 후 양원제(민의원, 참의원 별도)"),
    6: ("6th-general-1963", "1963-11-26", "전국구 도입"),
    7: ("7th-general-1967", "1967-06-08", ""),
    8: ("8th-general-1971", "1971-05-25", ""),
    9: ("9th-general-1973", "1973-02-27", "중선거구제 + 유정회(통일주체국민회의 선출)"),
    10: ("10th-general-1978", "1978-12-12", "중선거구제 + 유정회"),
    11: ("11th-general-1981", "1981-03-25", "중선거구제 + 전국구"),
    12: ("12th-general-1985", "1985-02-12", "중선거구제 + 전국구"),
}
DATE = {n: v[1].replace("-", "") for n, v in ROUNDS.items()}

# 전국구/유정회 정당별 의석 (위키 회수·공식). 6~8·11·12대=전국구(지역구 득표 배분),
# 9·10대=유정회(통일주체국민회의 선출·유신정우회 단일블록). 제헌~5대는 전국구 없음.
JEON: dict[int, dict[str, int]] = {
    6: {"민주공화당": 22, "민정당": 14, "민주당": 5, "자유민주당": 3},
    7: {"민주공화당": 27, "신민당": 17},
    8: {"민주공화당": 27, "신민당": 24},
    9: {"유신정우회": 73},   # 통대 선출 — 비례 아님(데이터상 nation seats로 표기)
    10: {"유신정우회": 77},
    11: {"민주정의당": 61, "민주한국당": 24, "한국국민당": 7},
    12: {"민주정의당": 61, "신한민주당": 17, "민주한국당": 9, "한국국민당": 5},
}


def raw_path(n: int):
    for p in RAW.glob(f"report_{n}th_*.json"):
        return p
    return None


def build(n: int):
    slug, date, note = ROUNDS[n]
    rp = raw_path(n)
    if not rp:
        print(f"  {n}대: raw 없음 — skip")
        return
    rows = json.loads(rp.read_text())
    by = defaultdict(list)
    for r in rows:
        by[(r["sido"], r["sgg"])].append(r)
    races, seat = [], defaultdict(int)
    for (sido, sgg), cs in sorted(by.items()):
        cs = sorted(cs, key=lambda c: -(c.get("votes") or 0))
        cands = []
        for i, c in enumerate(cs):
            cands.append({"name": c["name"], "party": c["party"], "votes": c.get("votes") or 0,
                          "pct": c.get("pct"), "rank": i + 1, "won": True})  # 당선인명부=전원 당선
            seat[c["party"]] += 1
        races.append({"sg_typecode": "2", "scope": "district", "sido": sido, "sigungu": sgg,
                      "district": sgg, "candidates": cands})
    # nation race(전국구) — JEON 있으면 채움, 없으면 빈 candidates(dist mode)
    jeon = JEON.get(n, {})
    nation = {"sg_typecode": "7", "scope": "nation", "sido": "전국", "sigungu": "전국",
              "candidates": [{"name": p, "party": p, "proportional_seats": s} for p, s in jeon.items()]}
    result = {"_meta": {"source": "nec-report-당선인명부", "is_final": True,
                        "election_date": date, "fetched_at": date},
              "races": races + [nation]}
    (RESULTS / f"{slug}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    # 등록 메타
    top = sorted(seat.items(), key=lambda x: -x[1])[:4]
    ctx = " · ".join(f"{p} {c}" for p, c in top)
    meta = {
        "id": slug, "name": f"제{n}대 국회의원선거", "kind": "general_election", "type": "general",
        "n": n, "date": date, "status": "archive",
        "nec": {"_note": "NEC 역대 당선인명부(info.nec report.xhtml)에서 지역구 당선인 회수"},
        "offices": [{"level": "국회의원", "sg_typecode": "2", "scope": "district"}],
        "results_file": f"data/results/{slug}.json",
        "_source_note": note,
        "archive": {
            "page": f"/archive/{slug}/", "results_path": f"data/results/{slug}.json",
            "polls_path": None, "exit_poll_path": None, "polls_window": None,
            "sg_typecode": "2", "proportional_sg_typecode": "7", "list_label": "확정",
            "context_note": (note + " — " if note else "") + ctx,
            "data_source_note": "NEC 역대 당선인명부 — 지역구 당선인(당선자 기준)" + (
                "" if jeon else " · 전국구/유정회 미반영(지역구만)"),
        },
    }
    (ELECTIONS / f"{slug}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    nwin = sum(seat.values())
    multi = sum(1 for cs in by.values() if len(cs) > 1)
    print(f"  {n}대 {slug}: 선거구 {len(races)} · 당선 {nwin} · 중선거구 {multi} · {ctx}")


def main():
    for n in ROUNDS:
        build(n)


if __name__ == "__main__":
    main()
