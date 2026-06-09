"""간선 대선(1·8~12대) 아카이브 — 시도별 직접투표 없는 간접선거. 어떤 간선이었는지를 핵심으로.
NEC 당선인명부에서 당선자 회수(data/raw/lod/pres_gansun.json) + 문서화된 후보 보강.

1대=제헌국회 / 8~11대=통일주체국민회의(유신) / 12대=대통령선거인단.
nation race(시도 없음). pres.js 히어로가 당선자+구도막대 렌더, 지도 섹션은 미표시.

사용: python scripts/build/build_gansun_pres.py   (이후 sync_archive_html.py)
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
ELECTIONS = ROOT / "data" / "elections"
INDEX = ELECTIONS / "index.json"

# n → (slug, 날짜, 간선방식, 설명, [후보(name,party,votes,pct)]). 당선자=NEC 확인, 차점=문서화.
GAN = {
    1:  ("1st-pres-1948",  "1948-07-20", "제헌국회 간접선거",
         "초대 대통령 — 제헌국회 국회의원 198인 투표로 선출",
         [("이승만", "대한독립촉성국민회", 180, 92.31), ("김구", "한국독립당", 13, 6.67), ("안재홍", "무소속", 2, 1.03)]),
    8:  ("8th-pres-1972",  "1972-12-23", "통일주체국민회의 간선 (유신헌법)",
         "유신체제 첫 대선 — 통일주체국민회의 대의원 2,359인이 단일후보 찬반 투표",
         [("박정희", "민주공화당", 2357, 99.92)]),
    9:  ("9th-pres-1978",  "1978-07-06", "통일주체국민회의 간선 (유신)",
         "통일주체국민회의 단일후보 — 박정희",
         [("박정희", "민주공화당", 2577, 99.96)]),
    10: ("10th-pres-1979", "1979-12-06", "통일주체국민회의 간선",
         "10·26 박정희 시해 후 — 통일주체국민회의가 최규하 권한대행 선출",
         [("최규하", "무소속", 2465, 96.70)]),
    11: ("11th-pres-1980", "1980-08-27", "통일주체국민회의 간선",
         "5·17 후 — 통일주체국민회의 단일후보 전두환",
         [("전두환", "민주정의당", 2524, 99.96)]),
    12: ("12th-pres-1981", "1981-02-25", "대통령선거인단 간선",
         "신헌법 — 대통령선거인단 5,278인 투표, 전두환 90.2%(야당 3인 출마)",
         [("전두환", "민주정의당", 4755, 90.23), ("유치송", "민주한국당", 404, 7.67),
          ("김종철", "한국국민당", 85, 1.61), ("김의택", "민권당", 26, 0.49)]),
}


def build(n):
    slug, date, method, desc, cands = GAN[n]
    nat_cands = [{"name": nm, "party": pty, "votes": v, "pct": pct, "rank": i + 1, "won": i == 0}
                 for i, (nm, pty, v, pct) in enumerate(cands)]
    total = sum(c[2] for c in cands)
    nation = {"sg_typecode": "1", "sido": "전국", "sigungu": "전국", "scope": "nation",
              "valid_votes": total, "candidates": nat_cands, "_indirect": method}
    result = {"_meta": {"source": "nec-당선인명부", "is_final": True, "election_date": date,
                        "indirect_election": method},
              "races": [nation]}
    (RESULTS / f"{slug}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    win = nat_cands[0]
    meta = {
        "id": slug, "name": f"제{n}대 대통령선거", "kind": "presidential", "type": "pres",
        "n": n, "date": date, "status": "archive",
        "nec": {"_note": "NEC 당선인명부 — 간선 당선자"},
        "offices": [{"level": "대통령", "sg_typecode": "1", "scope": "nation"}],
        "results_file": f"data/results/{slug}.json",
        "_source_note": f"[간선] {method} — {desc}",
        "archive": {
            "page": f"/archive/{slug}/", "results_path": f"data/results/{slug}.json",
            "polls_path": None, "exit_poll_path": None, "polls_window": None,
            "sg_typecode": "1", "list_label": "간선",
            "context_note": f"[{method}] {desc}",
            "data_source_note": f"간접선거 — {method}. 시도별 직접투표 없음(당선자·득표 기준).",
        },
    }
    (ELECTIONS / f"{slug}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"  {n}대 {slug}: {method} — {win['name']}({win['party']}) {win['pct']}%")
    return slug


def main():
    slugs = [build(n) for n in GAN]
    idx = json.loads(INDEX.read_text())
    have = set(idx["archive"])
    idx["archive"] += [s for s in slugs if s not in have]
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n")
    print(f"index 등록: {len(slugs)}개")


if __name__ == "__main__":
    main()
