"""옛 지선 1~4회(1995~2006) — 광역단체장·기초단체장·광역의원·기초의원 아카이브.
NEC 당선인명부 수집분(gov_1to4.json=tc3, loc_{n}.json=tc4·5·6)으로 main {id}.json(tc3) +
{id}.sigungu.json(tc4·5·6) 생성 + elections 메타 + index 등록. 한자명(name_hanja) 보존.

당선자 기준. 기초의원 정당공천은 4회(2006)부터 — 1~3회 tc6엔 정당 없음(무소속).
4회 tc6=중선거구(선거구당 2~4인). 비례(tc8·9)는 명부 구조 복잡 → 보류(scorecard 미표시).

사용: python scripts/build/build_old_local.py   (이후 sync_archive_html.py)
"""
from __future__ import annotations
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "lod"
RESULTS = ROOT / "data" / "results"
ELECTIONS = ROOT / "data" / "elections"
INDEX = ELECTIONS / "index.json"

ROUNDS = {
    1: ("1st-local-1995", "1995-06-27", "첫 전국동시지방선거 — 민선 자치 부활"),
    2: ("2nd-local-1998", "1998-06-04", "IMF 직후 — 국민회의·자민련 공조"),
    3: ("3rd-local-2002", "2002-06-13", "한나라당 광역 압승"),
    4: ("4th-local-2006", "2006-05-31", "한나라당 석권 — 기초의원 정당공천·중선거구 도입"),
}
_PARTYISH = re.compile(r"(당|연합|회|무소속|연대|총연맹)$")


def split_name(cell):
    name = re.sub(r"\(.*\)", "", cell or "").strip()
    m = re.search(r"\(([^)]+)\)", cell or "")
    return name, (m.group(1) if m else "")


def vp(cell):
    votes = int(re.sub(r"[^0-9]", "", (cell or "").split("(")[0]) or 0)
    pct = re.search(r"\(([\d.]+)", cell or "")
    return votes, (float(pct.group(1)) if pct else None)


def cand(name_cell, party, vcell, won=True):
    nm, hj = split_name(name_cell)
    v, p = vp(vcell)
    c = {"name": nm, "party": party, "votes": v, "pct": p, "won": won}
    if hj:
        c["name_hanja"] = hj
    return c


def build(n):
    slug, date, note = ROUNDS[n]
    gov = json.loads((RAW / "gov_1to4.json").read_text()).get(str(n), [])
    loc = json.loads((RAW / f"loc_{n}.json").read_text()) if (RAW / f"loc_{n}.json").exists() else {}
    if not gov:
        print(f"  {n}회: gov 없음")
        return None
    # tc=3 광역단체장 (main)
    tc3 = [{"sg_typecode": "3", "sido": g["sido"], "sigungu": "", "scope": "sido",
            "candidates": [{"name": g["name"], "party": g["party"], "votes": g["votes"],
                            "pct": g.get("pct"), "won": True,
                            **({"name_hanja": g["hanja"]} if g.get("hanja") else {})}]}
           for g in gov]
    sig_races = []
    seat = defaultdict(int)
    for g in gov:
        seat["광역단체장"] += 1
    # tc=4 기초단체장 (구시군별 1인)
    for sido, rows in (loc.get("4") or {}).items():
        for r in rows:
            sig_races.append({"sg_typecode": "4", "sido": sido, "sigungu": r[0], "scope": "sigungu",
                              "candidates": [cand(r[2], r[1], r[-1])]})
            seat["기초단체장"] += 1
    # tc=5 광역의원 지역구 (선거구별 1인): [구시군, 선거구, 정당, 성명, ..., 득표]
    for sido, rows in (loc.get("5") or {}).items():
        for r in rows:
            sig_races.append({"sg_typecode": "5", "sido": sido, "sigungu": r[0], "scope": "district",
                              "district": r[1], "candidates": [cand(r[3], r[2], r[-1])]})
            seat["광역의원"] += 1
    # tc=6 기초의원 지역구: 1~3회 [구시군,선거구,성명,...](무소속), 4회 [구시군,선거구,정당,성명,...](중선거구 다인)
    by6 = defaultdict(list)
    for sido, rows in (loc.get("6") or {}).items():
        for r in rows:
            has_party = len(r) >= 10 and bool(_PARTYISH.search(r[2]))
            party = r[2] if has_party else "무소속"
            name_cell = r[3] if has_party else r[2]
            by6[(sido, r[0], r[1])].append((name_cell, party, r[-1]))
    for (sido, sgg, dist), cs in by6.items():
        sig_races.append({"sg_typecode": "6", "sido": sido, "sigungu": sgg, "scope": "district",
                          "district": dist, "seats_total": len(cs),
                          "candidates": [cand(nc, pty, vc) for nc, pty, vc in cs]})
        for _ in cs:
            seat["기초의원"] += 1
    main = {"_meta": {"election": f"제{n}회 전국동시지방선거", "election_id": slug,
                      "election_date": date, "is_final": True, "source": "nec-당선인명부",
                      "chunked": True, "sigungu_file": "sigungu",
                      "_caveat": "비례(광역·기초)는 미반영 — 지역구·단체장만"},
            "races": tc3}
    sig = {"_meta": {"election_id": slug, "chunk": "sigungu"}, "races": sig_races}
    (RESULTS / f"{slug}.json").write_text(json.dumps(main, ensure_ascii=False, indent=2) + "\n")
    (RESULTS / f"{slug}.sigungu.json").write_text(json.dumps(sig, ensure_ascii=False, indent=2) + "\n")
    pc = Counter(g["party"] for g in gov)
    meta = {
        "id": slug, "name": f"제{n}회 전국동시지방선거", "kind": "local", "type": "local",
        "n": n, "date": date, "status": "archive",
        "nec": {"_note": "NEC 당선인명부 — 단체장·지역구의원(한자명 포함)"},
        "offices": [{"level": "광역단체장", "sg_typecode": "3", "scope": "sido"},
                    {"level": "기초단체장", "sg_typecode": "4", "scope": "sigungu"},
                    {"level": "광역의원", "sg_typecode": "5", "scope": "district"},
                    {"level": "기초의원", "sg_typecode": "6", "scope": "district"}],
        "results_file": f"data/results/{slug}.json",
        "_source_note": note,
        "_data_caveat": "비례대표(광역·기초) 미반영 — 단체장·지역구의원만(당선자 기준).",
        "archive": {
            "page": f"/archive/{slug}/", "results_path": f"data/results/{slug}.json",
            "polls_path": None, "exit_poll_path": None, "polls_window": None,
            "sg_typecode": "3", "proportional_sg_typecode": "8", "list_label": "확정",
            "context_note": (note + " — " if note else "") + "광역단체장 " + " · ".join(f"{p} {c}" for p, c in pc.most_common(3)),
            "data_source_note": "NEC 당선인명부 — 단체장·지역구의원(비례 미반영).",
        },
    }
    (ELECTIONS / f"{slug}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"  {n}회 {slug}: " + " ".join(f"{k}{v}" for k, v in seat.items()))
    return slug


def main():
    slugs = [s for s in (build(n) for n in ROUNDS) if s]
    idx = json.loads(INDEX.read_text())
    have = set(idx["archive"])
    idx["archive"] += [s for s in slugs if s not in have]
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n")
    print(f"index: {slugs}")


if __name__ == "__main__":
    main()
