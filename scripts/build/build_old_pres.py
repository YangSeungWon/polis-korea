"""옛 직선 대선(2·3·5·6·7대) — NEC 개표현황 시도별 수집분(data/raw/lod/pres_*.json)으로
results/{id}.json(nation+시도 race) + elections/{id}.json + index 등록.

nation = 시도 합산. 시도 race = 시도별 후보 득표(→ 대선 지도). pres.js 렌더러 사용.
간선 대선(1·8~12대)·부정선거 4대는 제외(시도별 직접투표 없음).

사용: python scripts/build/build_old_pres.py   (이후 sync_archive_html.py)
"""
from __future__ import annotations
import json
import re
from collections import defaultdict
from pathlib import Path


def parse_sido(d):
    """개표현황 {ths(thead textContent), tds(합계행)} → [{party,name,votes}].
    후보 = '...득표율(%)' 라벨 뒤 ~ '계' 앞. 정당+성명 concat → 성명=뒤 3글자(이 시대 3글자명)."""
    if not isinstance(d, dict) or "ths" not in d:
        return []
    ths, tds = d["ths"], d["tds"]
    start = next((i + 1 for i, t in enumerate(ths) if "득표율" in t), None)
    if start is None:
        return []
    end = ths.index("계") if "계" in ths else len(ths)
    names = ths[start:end]
    nums = [int(re.sub(r"[^0-9]", "", str(x)) or 0) for x in tds]
    # tds = [합계명칭, 선거인수, 투표수, c1..cN, 계, 무효, 기권] → 후보 득표 nums[3:3+N]
    out = []
    for i, nc in enumerate(names):
        v = nums[3 + i] if 3 + i < len(nums) else 0
        name = nc[-3:]
        party = nc[:-3] or "무소속"
        out.append({"party": party, "name": name, "votes": v})
    return out

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "lod"
RESULTS = ROOT / "data" / "results"
ELECTIONS = ROOT / "data" / "elections"
INDEX = ELECTIONS / "index.json"

# n → (slug, 선거일 YYYY-MM-DD, 비고)
ROUNDS = {
    2: ("2nd-pres-1952", "1952-08-05", "발췌개헌 후 첫 직선 — 이승만 재선"),
    3: ("3rd-pres-1956", "1956-05-15", "신익희 급서 — 이승만 3선"),
    5: ("5th-pres-1963", "1963-10-15", "박정희 vs 윤보선 — 15만표차 신승"),
    6: ("6th-pres-1967", "1967-05-03", "박정희 재선"),
    7: ("7th-pres-1971", "1971-04-27", "박정희 vs 김대중"),
}
DATE = {n: v[1].replace("-", "") for n, v in ROUNDS.items()}
# 직선 대선 주요 후보 한자(확정). 개표현황엔 한자 없어 별도 맵.
HANJA = {"이승만": "李承晩", "조봉암": "曺奉岩", "이시영": "李始榮", "신흥우": "申興雨",
         "박정희": "朴正熙", "윤보선": "尹潽善", "변영태": "卞榮泰", "김대중": "金大中",
         "신익희": "申翼熙", "김준연": "金俊淵", "전진한": "錢鎭漢"}
SIDO_ORDER = ["서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "경기도",
              "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도",
              "경상북도", "경상남도", "제주특별자치도"]


def raw_path(n):
    for p in RAW.glob(f"pres_{n}_*.json"):
        return p
    return None


def build(n):
    slug, date, note = ROUNDS[n]
    rp = raw_path(n)
    if not rp:
        print(f"  {n}대: raw 없음")
        return None
    data = json.loads(rp.read_text())
    # nation 합산: (name, party) → votes
    natv = defaultdict(int)
    party_of = {}
    sido_races = []
    for sido in SIDO_ORDER:
        cs = parse_sido(data.get(sido))
        if not cs:
            continue
        total = sum(c["votes"] for c in cs) or 1
        scs = sorted(cs, key=lambda c: -c["votes"])
        cands = [{"name": c["name"], "party": c["party"], "votes": c["votes"],
                  "pct": round(c["votes"] / total * 100, 2), "rank": i + 1, "won": i == 0,
                  **({"name_hanja": HANJA[c["name"]]} if c["name"] in HANJA else {})}
                 for i, c in enumerate(scs)]
        sido_races.append({"sg_typecode": "1", "sido": sido, "sigungu": sido, "scope": "sido",
                           "valid_votes": total, "candidates": cands})
        for c in cs:
            natv[c["name"]] += c["votes"]
            party_of[c["name"]] = c["party"]
    if not natv:
        print(f"  {n}대: 데이터 없음")
        return None
    ntotal = sum(natv.values()) or 1
    nat = sorted(natv.items(), key=lambda x: -x[1])
    nat_cands = [{"name": nm, "party": party_of[nm], "votes": v,
                  "pct": round(v / ntotal * 100, 2), "rank": i + 1, "won": i == 0,
                  **({"name_hanja": HANJA[nm]} if nm in HANJA else {})}
                 for i, (nm, v) in enumerate(nat)]
    nation = {"sg_typecode": "1", "sido": "전국", "sigungu": "전국", "scope": "nation",
              "valid_votes": ntotal, "candidates": nat_cands}
    result = {"_meta": {"source": "nec-report-개표현황", "is_final": True, "election_date": date},
              "races": [nation] + sido_races}
    (RESULTS / f"{slug}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    win, sec = nat_cands[0], (nat_cands[1] if len(nat_cands) > 1 else None)
    ctx = f"{win['name']}({win['party']}) {win['pct']}%" + (f" / {sec['name']} {sec['pct']}%" if sec else "")
    meta = {
        "id": slug, "name": f"제{n}대 대통령선거", "kind": "presidential", "type": "pres",
        "n": n, "date": date, "status": "archive",
        "nec": {"_note": "NEC 역대 개표현황(info.nec)에서 시도별 후보 득표 회수"},
        "offices": [{"level": "대통령", "sg_typecode": "1", "scope": "nation"}],
        "results_file": f"data/results/{slug}.json",
        "_source_note": note,
        "archive": {
            "page": f"/archive/{slug}/", "results_path": f"data/results/{slug}.json",
            "polls_path": None, "exit_poll_path": None, "polls_window": None,
            "sg_typecode": "1", "list_label": "확정",
            "context_note": (note + " — " if note else "") + ctx,
            "data_source_note": "NEC 역대 개표현황 — 시도별 후보 득표(합계)",
        },
    }
    (ELECTIONS / f"{slug}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"  {n}대 {slug}: 시도 {len(sido_races)} · {ctx}")
    return slug


def main():
    slugs = [s for s in (build(n) for n in ROUNDS) if s]
    idx = json.loads(INDEX.read_text())
    have = set(idx["archive"])
    idx["archive"] += [s for s in slugs if s not in have]
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n")
    print(f"index 등록: {slugs}")


if __name__ == "__main__":
    main()
