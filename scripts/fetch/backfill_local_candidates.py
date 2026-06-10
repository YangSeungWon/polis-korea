"""옛 지선 광역·기초단체장 race를 NEC 투·개표 API의 전체 후보로 교체(백필).

기존 1~4회 생산 데이터는 '당선인명부'라 race당 후보 1명(당선자)만 있고, 광역장은
votes도 깨져 있어 resultForSido 재계산 시 100%로 표시됨. 투·개표 API
(getXmntckSttusInfoInqire)는 3·4회(2002·2006)부터 후보별 득표(jd/hbj/dugsu)를
제공 → 이를 받아 생산 {id}.json(광역장 tc3) · {id}.sigungu.json(기초장 tc4)의
candidates를 전원 후보·실제 득표·득표율·선거인/투표수로 교체.

1·2회(1995·1998)는 이 API에 없음(INFO-03) → LOD 등 별도.

행 필터:
  tc3 광역장: wiwName='합계' & sdName='합계' → sggName=시도. 시도 total.
  tc4 기초장: wiwName='합계' & sdName≠'합계' → sdName=시도, sggName=시군구.

당선자 name_hanja는 기존 데이터에서 이름 매칭으로 보존.

사용: NEC_API_KEY=... python3 scripts/fetch/backfill_local_candidates.py --rounds 3,4
"""
from __future__ import annotations
import argparse, json, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"
API = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire"

SG_ID = {3: "20020613", 4: "20060531"}
ELECTION_ID = {3: "3rd-local-2002", 4: "4th-local-2006"}
# API는 선거 당시 옛 시도명(강원도 등), 생산 기초장은 현 캐노니컬명을 쓰기도 함 → 양쪽 시도 키 모두 시도.
SIDO_CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도"}
_base = lambda s: re.sub(r"\([^)]*\)$", "", s or "")   # '고성군(강원)'→'고성군' 접미사 무시


def fetch_rows(key, sg_id, tc):
    """투·개표 API 전 페이지 → item element 리스트. (API가 numOfRows를 캡하므로 실제 누적건수로 페이징.)"""
    out, page, total = [], 1, None
    while True:
        p = {"serviceKey": key, "pageNo": page, "numOfRows": 100,
             "sgId": sg_id, "sgTypecode": tc}
        url = API + "?" + urllib.parse.urlencode(p, safe="")
        root = ET.fromstring(urllib.request.urlopen(url, timeout=40).read().decode("utf-8", "replace"))
        items = root.findall(".//item")
        if not items:
            break
        out.extend(items)
        if total is None:
            total = int(root.findtext(".//totalCount") or 0)
        if len(out) >= total:
            break
        page += 1
        time.sleep(0.2)
    return out


def candidates_from(it):
    """item → (candidates[], electors, voted). pct=dugsu/유효합*100."""
    cs = []
    for i in range(1, 51):
        nm = (it.findtext(f"hbj{i:02d}") or "").strip()
        if not nm:
            continue
        votes = int(it.findtext(f"dugsu{i:02d}") or 0)
        party = (it.findtext(f"jd{i:02d}") or "").strip() or "무소속"
        cs.append({"name": nm, "party": party, "votes": votes})
    tot = sum(c["votes"] for c in cs) or 1
    cs.sort(key=lambda c: -c["votes"])
    for rank, c in enumerate(cs, 1):
        c["pct"] = round(c["votes"] / tot * 100, 1)
        c["rank"] = rank
        c["won"] = rank == 1
    electors = int(it.findtext("sunsu") or 0)
    voted = int(it.findtext("tusu") or 0)
    return cs, electors, voted


def preserve_hanja(new_cands, old_cands):
    hj = {c.get("name"): c.get("name_hanja") for c in (old_cands or []) if c.get("name_hanja")}
    for c in new_cands:
        if c["name"] in hj:
            c["name_hanja"] = hj[c["name"]]


def patch_race(race, cands, electors, voted):
    preserve_hanja(cands, race.get("candidates"))
    race["candidates"] = cands
    if electors:
        race["electors"] = electors
        race["voted"] = voted
        race["turnout"] = round(voted / electors * 100, 2) if electors else None


def main(rounds):
    key = os.environ["NEC_API_KEY"]
    for n in rounds:
        sg_id, eid = SG_ID[n], ELECTION_ID[n]
        main_p = RESULTS / f"{eid}.json"
        sgg_p = RESULTS / f"{eid}.sigungu.json"
        md = json.loads(main_p.read_text(encoding="utf-8"))
        sd = json.loads(sgg_p.read_text(encoding="utf-8"))

        # 광역장 (tc3) — 시도 total 행
        gov = {}  # sido → (cands, electors, voted)
        for it in fetch_rows(key, sg_id, 3):
            if it.findtext("wiwName") == "합계" and it.findtext("sdName") == "합계":
                gov[it.findtext("sggName")] = candidates_from(it)
        g_hit = 0
        for r in md["races"]:
            if r.get("sg_typecode") == "3" and r.get("sido") in gov:
                patch_race(r, *gov[r["sido"]]); g_hit += 1
        g_miss = sorted(s for s in gov if s not in {r.get("sido") for r in md["races"] if r.get("sg_typecode") == "3"})

        # 기초장 (tc4) — (시도,시군구) total 행. 시도 canon + 시군구 접미사 무시로 매칭.
        gicho = {}  # (canon시도, base시군구) → (cands, electors, voted)
        for it in fetch_rows(key, sg_id, 4):
            if it.findtext("wiwName") == "합계" and it.findtext("sdName") != "합계":
                sido = it.findtext("sdName")
                key2 = (SIDO_CANON.get(sido, sido), _base(it.findtext("sggName")))
                gicho[key2] = candidates_from(it)
        m_hit, used = 0, set()
        for r in sd["races"]:
            if r.get("sg_typecode") == "4":
                k = (SIDO_CANON.get(r.get("sido"), r.get("sido")), _base(r.get("sigungu")))
                if k in gicho:
                    patch_race(r, *gicho[k]); m_hit += 1; used.add(k)
        m_miss = sorted(k for k in gicho if k not in used)

        md.setdefault("_meta", {})["source"] = "nec-투개표API(후보전원) + 당선인명부(한자)"
        md["_meta"].pop("_caveat", None)
        sd.setdefault("_meta", {})["source"] = md["_meta"]["source"]
        main_p.write_text(json.dumps(md, ensure_ascii=False, indent=1), encoding="utf-8")
        sgg_p.write_text(json.dumps(sd, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{n}회({eid}): 광역장 {g_hit}/{len(gov)} 패치"
              f"{' 미매칭'+str(g_miss) if g_miss else ''} | 기초장 {m_hit}/{len(gicho)} 패치"
              f"{' API여분'+str(m_miss[:8]) if m_miss else ''}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", default="3,4")
    a = ap.parse_args()
    main([int(x) for x in a.rounds.split(",")])
