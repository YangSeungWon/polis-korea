"""person-index에 국회의원 assembly_id·한자·비례 보강.

build_person_index가 이미 (이름+생년월일)로 인물을 분리하므로, 여기서는 재클러스터링 없이:
  1. 각 인물 entry에 assembly_id 부여 — 생년월일이 assembly_map(MONA 기준)과 일치하면 그 id,
     없으면(옛 선거·dob 미상) 총선 경력(회차+지역구)으로 best-effort 매칭.
  2. 비례대표·전국구 국회의원 보강 — 결과 데이터엔 개별 비례 인물이 없어, assembly_map에서
     해당 인물(같은 dob)에 비례 race 주입(없으면 신규 entry).

Output: assets/person-index.json (덮어씀).
"""
from __future__ import annotations
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from party_canon import disambiguate_party  # noqa: E402

PERSON_IDX = ROOT / "assets/person-index.json"
ASSEMBLY_MAP = ROOT / "data/raw/assembly_member_map.json"


def normalize_district(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def eid_to_assembly_n(eid: str):
    m = re.match(r"(\d+)(?:st|nd|rd|th)-general-", eid)
    return int(m.group(1)) if m else None


def match_by_career(nm, dob, races, by_name):
    """dob 미일치/미상 entry → 총선 경력(회차+지역구)으로 assembly_id best-effort."""
    cands = by_name.get(nm, [])
    if dob:
        cands = [p for p in cands if p.get("dob") == dob] or cands
    if not cands:
        return None
    votes = defaultdict(int)
    for r in races:
        n = eid_to_assembly_n(r["eid"])
        if n is None:
            continue
        place = normalize_district(r.get("place", ""))
        for p in cands:
            for c in p["careers"]:
                if c["n"] != n:
                    continue
                their = normalize_district(c.get("district", ""))
                if their and place and (their in place or place in their
                                        or ("비례" in place and "비례" in their)):
                    votes[p["id"]] += 1
    return max(votes, key=votes.get) if votes else None


def main():
    person = json.loads(PERSON_IDX.read_text(encoding="utf-8"))
    asm = json.loads(ASSEMBLY_MAP.read_text(encoding="utf-8"))
    asm_by_id = {p["id"]: p for p in asm["persons"]}
    by_name = defaultdict(list)
    for p in asm["persons"]:
        by_name[p["name"]].append(p)

    ej = json.loads((ROOT / "data/elections.json").read_text(encoding="utf-8"))
    TERM_DATE = {e["n"]: e.get("date", "") for e in ej.get("national_assembly", {}).get("elections", []) if e.get("date")}

    # 1) assembly_id 부여 — dob 우선, 없으면 경력 매칭
    n_aid = 0
    for e in person["persons"]:
        nm, dob = e["name"], e.get("dob")
        aid = f"{nm}_{dob}" if dob and f"{nm}_{dob}" in asm_by_id else None
        if not aid:
            aid = match_by_career(nm, dob, e["races"], by_name)
        if aid:
            ap = asm_by_id[aid]
            e["assembly_id"] = aid
            e["id"] = aid
            if not e.get("dob"):
                e["dob"] = ap.get("dob")
            if not e.get("hanja"):
                e["hanja"] = ap.get("hanja")
            n_aid += 1

    # 2) 비례대표·전국구 보강
    by_aid = {e["assembly_id"]: e for e in person["persons"] if e.get("assembly_id")}
    n_bir_add = n_bir_new = 0
    for ap in asm["persons"]:
        birs = [c for c in ap["careers"]
                if "비례" in (c.get("district") or "") or "전국" in (c.get("district") or "")]
        if not birs:
            continue
        races = []
        for c in birs:
            dt = TERM_DATE.get(c["n"], "")
            races.append({"eid": f"general-{c['n']}", "year": int(dt[:4]) if dt[:4].isdigit() else None,
                          "round": f"{c['n']}대 총선", "date": dt, "place": "비례대표",
                          "party": disambiguate_party(c.get("party") or "", dt),
                          "pct": None, "rank": None, "won": True, "tc": "7"})

        def rebuild(entry):
            entry["races"].sort(key=lambda r: (r.get("date") or "", r.get("eid")))
            seen = []
            for r in entry["races"]:
                if r["party"] and r["party"] not in seen:
                    seen.append(r["party"])
            entry["parties"] = seen[:6]
            entry["wins"] = sum(1 for r in entry["races"] if r["won"])
            entry["losses"] = sum(1 for r in entry["races"] if not r["won"])

        e = by_aid.get(ap["id"])
        if e:
            have = {(r.get("round"), r.get("tc")) for r in e["races"]}
            fresh = [r for r in races if (r["round"], "7") not in have]
            if fresh:
                e["races"] += fresh
                rebuild(e)
                n_bir_add += 1
        else:
            entry = {"name": ap["name"], "id": ap["id"], "assembly_id": ap["id"],
                     "dob": ap.get("dob"), "hanja": ap.get("hanja"),
                     "sidos": [], "likely_namesake": False, "races": races}
            rebuild(entry)
            person["persons"].append(entry)
            by_aid[ap["id"]] = entry
            n_bir_new += 1

    person["persons"].sort(key=lambda p: (-len(p["races"]), -p.get("wins", 0), p["name"]))
    person["_meta"]["n_persons"] = len(person["persons"])
    person["_meta"]["assembly_matched"] = n_aid
    PERSON_IDX.write_text(json.dumps(person, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"→ {PERSON_IDX.relative_to(ROOT)}: {len(person['persons'])} persons · aid {n_aid} · 비례 보강 +{n_bir_add}/{n_bir_new}")


if __name__ == "__main__":
    main()
