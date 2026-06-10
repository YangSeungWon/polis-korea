"""scrape된 1·2회 지선 전체 후보(data/raw/nec/local_old_{n}.json)를 생산 데이터에 패치.

info.nec VCCP09 스크랩(fetch_local_old_results.mjs) → 광역장 {id}.json(tc3)·
기초장 {id}.sigungu.json(tc4)의 candidates를 당선자만→전원 후보·실제 득표·득표율로 교체.
3·4회 backfill_local_candidates.py와 동일 패턴(시도 canon·시군구 접미사 무시·한자 보존).

사용: python3 scripts/build/patch_local_old.py
"""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"
RAW = ROOT / "data/raw/nec"
ELECTION_ID = {1: "1st-local-1995", 2: "2nd-local-1998"}
SIDO_CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도"}
_base = lambda s: re.sub(r"\([^)]*\)$", "", s or "")


def to_cands(entry, old_cands):
    cs = [{"name": c["name"], "party": c["party"], "votes": c["votes"]} for c in entry["candidates"]]
    tot = sum(c["votes"] for c in cs) or 1
    cs.sort(key=lambda c: -c["votes"])
    hj = {c.get("name"): c.get("name_hanja") for c in (old_cands or []) if c.get("name_hanja")}
    for rank, c in enumerate(cs, 1):
        c["pct"] = round(c["votes"] / tot * 100, 1)
        c["rank"] = rank
        c["won"] = rank == 1
        if c["name"] in hj:
            c["name_hanja"] = hj[c["name"]]
    return cs


def apply(race, entry):
    race["candidates"] = to_cands(entry, race.get("candidates"))
    if entry.get("electors"):
        race["electors"] = entry["electors"]
        race["voted"] = entry["voted"]
        race["turnout"] = round(entry["voted"] / entry["electors"] * 100, 2)


def main():
    for n, eid in ELECTION_ID.items():
        raw = json.loads((RAW / f"local_old_{n}.json").read_text(encoding="utf-8"))
        gov = {SIDO_CANON.get(s, s): v for s, v in raw["gov"].items()}
        gicho = {}
        for k, v in raw["gicho"].items():
            s, sgg = k.split("|", 1)
            gicho[(SIDO_CANON.get(s, s), _base(sgg))] = v

        mp = RESULTS / f"{eid}.json"
        sp = RESULTS / f"{eid}.sigungu.json"
        md = json.loads(mp.read_text(encoding="utf-8"))
        sd = json.loads(sp.read_text(encoding="utf-8"))

        g_hit, g_keys = 0, set()
        for r in md["races"]:
            if r.get("sg_typecode") == "3":
                g_keys.add(SIDO_CANON.get(r.get("sido"), r.get("sido")))
                k = SIDO_CANON.get(r.get("sido"), r.get("sido"))
                if k in gov:
                    apply(r, gov[k]); g_hit += 1
        g_miss = sorted(s for s in gov if s not in g_keys)

        m_hit, used = 0, set()
        for r in sd["races"]:
            if r.get("sg_typecode") == "4":
                k = (SIDO_CANON.get(r.get("sido"), r.get("sido")), _base(r.get("sigungu")))
                if k in gicho:
                    apply(r, gicho[k]); m_hit += 1; used.add(k)
        m_miss = sorted(k for k in gicho if k not in used)

        for d in (md, sd):
            d.setdefault("_meta", {})["source"] = "nec-개표현황(VCCP09, 후보전원) + 당선인명부(한자)"
            d["_meta"].pop("_caveat", None)
        mp.write_text(json.dumps(md, ensure_ascii=False, indent=1), encoding="utf-8")
        sp.write_text(json.dumps(sd, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{n}회({eid}): 광역 {g_hit}/{len(gov)}{' miss'+str(g_miss) if g_miss else ''} | "
              f"기초 {m_hit}/{len(gicho)}{' 여분'+str(m_miss[:6]) if m_miss else ''}")


if __name__ == "__main__":
    main()
