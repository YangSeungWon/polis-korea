"""인물 인덱스 — 모든 회차 candidate를 이름 기준으로 묶어 타임라인 생성.

Output: assets/person-index.json
스키마:
  { "_meta": {...},
    "persons": [
      { "name": "이재명", "id": "이재명",
        "wins": N, "losses": M,
        "parties": [...], "sidos": [...],
        "races": [{"eid","year","round","place","party","pct","rank","won"}, ...] }
    ] }

휴리스틱: 같은 election 안 (name, party) 다중 row(시도별 분해)는 시도 set
모아 1건으로 통합. 회차 간 결합은 이름만 기준 (MVP). 동명이인 split은 UI에서
시도 set·정당 패밀리 보고 사람이 판단.
"""
from __future__ import annotations
import json
import glob
import re
from collections import defaultdict
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 정당명 정규화 공용 모듈 (같은 디렉터리) — registry.json 단일 출처.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from party_canon import canon_party, disambiguate_party  # noqa: E402

OUT = ROOT / "assets/person-index.json"


KIND_SHORT = {"pres": "대선", "general": "총선", "local": "지선"}
NTH_UNIT = {"pres": "대", "general": "대", "local": "회"}


def round_label(eid: str) -> str:
    """13th-pres-1987 → '13대 대선'. byelection-2020-04-15 → '2020-04-15 재보궐'."""
    if eid.startswith("byelection-"):
        return f"{eid.replace('byelection-','')} 재보궐"
    m = re.match(r"(\d+)(?:st|nd|rd|th)?-(\w+)-\d+", eid)
    if not m:
        return eid
    n, kind = m.groups()
    return f"{n}{NTH_UNIT.get(kind, '')} {KIND_SHORT.get(kind, kind)}".strip()


# 정당 캐노니컬 — 통합 후 같은 가족으로 보일 라벨 (선택적).
PARTY_FAMILY = {
    "통일민주당": "민주계열", "민주당": "민주계열", "새정치국민회의": "민주계열",
    "새천년민주당": "민주계열", "열린우리당": "민주계열", "민주통합당": "민주계열",
    "새정치민주연합": "민주계열", "더불어민주당": "민주계열", "더불어민주연합": "민주계열",
    "민주자유당": "보수계열", "신한국당": "보수계열", "한나라당": "보수계열",
    "새누리당": "보수계열", "자유한국당": "보수계열", "미래통합당": "보수계열",
    "국민의힘": "보수계열", "국민의미래": "보수계열",
}


def main():
    # 후보 생년월일·한자 (NEC bio) — 동명이인 dob 분리용.
    bio_by = defaultdict(list)
    bio_path = ROOT / "data/raw/nec_candidate_bio.json"
    if bio_path.exists():
        for r in json.loads(bio_path.read_text(encoding="utf-8")).get("records", []):
            bio_by[(r["name"], r["sgId"])].append(r)

    def _nm(s):
        return re.sub(r"\s", "", s or "")

    def match_bio(name, date, place, tc):
        """(이름, 선거일, 선거구, 직위tc) → (생년월일 YYYY-MM-DD, 한자) 또는 (None, None)."""
        recs = bio_by.get((name, (date or "").replace("-", "")[:8]))
        if not recs:
            return None, None
        if len(recs) == 1:
            r = recs[0]
        else:  # 같은 선거 동명이인 — 직위(tc) + 선거구로 분별
            cand = [x for x in recs if str(x.get("tc")) == str(tc)] or recs
            p = _nm(place)
            r = next((x for x in cand if p and (_nm(x["sgg"]) == p or _nm(x["sd"]) == p
                      or p in _nm(x["sgg"]) or _nm(x["sgg"]) in p)), None)
            if r is None and len(cand) == 1:
                r = cand[0]
            if r is None:
                return None, None
        bd = r.get("birthday") or ""
        dob = f"{bd[:4]}-{bd[4:6]}-{bd[6:8]}" if len(bd) == 8 else None
        return dob, (r.get("hanja") or None)

    # 국회의원 명부(assembly_map) — 옛 의원 dob/한자(전 시대). 총선 race 분리에 보강.
    asm_careers = defaultdict(list)
    asm_path = ROOT / "data/raw/assembly_member_map.json"
    if asm_path.exists():
        for p in json.loads(asm_path.read_text(encoding="utf-8")).get("persons", []):
            for c in p.get("careers", []):
                asm_careers[(p["name"], c["n"])].append((p.get("dob"), p.get("hanja"), c.get("district", "")))

    def match_assembly(name, eid, place):
        """총선 race → assembly_map(이름+회차+지역구)로 (dob, 한자). 비의원·미매칭이면 (None, None)."""
        m = re.match(r"(\d+)(?:st|nd|rd|th)-general-", eid)
        if not m:
            return None, None
        recs = asm_careers.get((name, int(m.group(1))))
        if not recs:
            return None, None
        if len(recs) == 1:
            return recs[0][0], recs[0][1]
        p = _nm(place)
        for dob, hanja, dist in recs:  # 동명 의원 — 지역구로 분별
            d = _nm(dist)
            if p and d and (d in p or p in d):
                return dob, hanja
        return None, None

    # 1단계: per (eid, name, party) 통합 — 시도별 분해 row → 1건
    per_eid: dict = defaultdict(lambda: defaultdict(list))
    eid_meta = {}

    for f in sorted(glob.glob(str(ROOT / "data/results/*.json"))):
        fname = Path(f).name
        if ".sigungu" in fname:
            continue
        if "byelection-" not in fname and not any(
                t in fname for t in ["general", "pres", "local"]):
            continue
        eid = fname.replace(".json", "")
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        meta = d.get("_meta", {})
        date = meta.get("election_date", "") or ""
        year = int(date[:4]) if date and date[:4].isdigit() else None
        eid_meta[eid] = {"year": year, "round": round_label(eid), "date": date}

        # 기초장(tc4) 등 sigungu-level race는 청크 파일에 — 같이 읽어야 기초단체장 이력이 들어옴.
        races = list(d.get("races", []))
        sgg_f = Path(f).with_suffix("").as_posix() + ".sigungu.json"
        if Path(sgg_f).exists():
            try:
                races += json.load(open(sgg_f, encoding="utf-8")).get("races", [])
            except Exception:
                pass

        # 인물 타임라인에 넣을 직위: 대통령·국회의원·광역장·기초장·교육감만.
        #   의원(5·6)·비례(7·8·9)는 제외(수천 명·정당명 행). canonical scope만 통과.
        CANON_SCOPE = {"1": "nation", "2": "district", "3": "sido", "4": "sigungu", "11": "sido"}

        for race in races:
            tc = race.get("sg_typecode", "")
            scope = race.get("scope", "")
            expected = CANON_SCOPE.get(tc)
            if not expected or scope != expected:
                continue
            sido = race.get("sido", "") or ""
            sigungu = race.get("sigungu", "") or ""
            district = race.get("district", "") or ""
            place = sigungu or district or sido or "전국"
            for c in race.get("candidates", []):
                nm = (c.get("name") or "").strip()
                if not nm:
                    continue
                party = disambiguate_party((c.get("party") or "").strip(), date)  # 별칭→정식명 + '민주당' 날짜분기
                votes = c.get("votes", 0) or 0
                rank = c.get("rank") or 99
                won = bool(c.get("won")) or (rank == 1)
                dob, hanja = match_bio(nm, date, place, tc)
                if (not dob or not hanja) and tc == "2":   # 총선 → assembly_map 보강(옛 의원)
                    adob, ahanja = match_assembly(nm, eid, place)
                    dob = dob or adob
                    hanja = hanja or ahanja
                per_eid[eid][(nm, party)].append({
                    "sido": sido, "place": place, "tc": tc,
                    "rank": rank, "won": won,
                    "pct": c.get("pct"), "votes": votes,
                    "dob": dob, "hanja": hanja,
                })

    # 2단계: per (eid, name, party) → 1건으로 통합 (최다득표 row 기준)
    flat = []
    for eid, by_np in per_eid.items():
        m = eid_meta.get(eid, {})
        for (nm, party), rows in by_np.items():
            best = max(rows, key=lambda r: r["votes"] or 0)
            sidos = sorted(set(r["sido"] for r in rows if r["sido"]))
            won_any = any(r["won"] for r in rows)
            flat.append({
                "name": nm, "party": party,
                "eid": eid, "year": m.get("year"), "round": m.get("round"), "date": m.get("date"),
                "place": best["place"], "sidos": sidos,
                "pct": best.get("pct"), "rank": best["rank"],
                "won": won_any,
                "tc": best.get("tc"),
                "dob": next((r["dob"] for r in rows if r.get("dob")), None),
                "hanja": next((r["hanja"] for r in rows if r.get("hanja")), None),
            })

    # 3단계: (이름+생년월일) cluster — dob 있으면 동명이인 분리, 없으면(옛 선거) 이름 단위.
    by_name = defaultdict(list)
    for r in flat:
        by_name[r["name"]].append(r)

    persons = []
    for nm, rows in by_name.items():
        # 동명이인 분리 — union-find. 같은 생년 또는 같은 한자면 동일인; 둘 다 미상이면
        # 같은 시도 + 가까운 연도(≤16년)면 동일인(한 정치인의 연속 경력). 다른 생년/다른 한자는
        # 절대 병합 금지. (옛 선거 낙선자는 생년·한자 미상이라 시도+연도로 군집해야 함.)
        n = len(rows)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(n):
            for j in range(i + 1, n):
                a, b = rows[i], rows[j]
                da, db = a.get("dob"), b.get("dob")
                ha, hb = a.get("hanja"), b.get("hanja")
                if da and db and da != db:
                    continue
                if ha and hb and ha != hb:
                    continue
                link = (da and da == db) or (ha and ha == hb)
                if not link:
                    sa, sb = set(a["sidos"]), set(b["sidos"])
                    link = bool(sa & sb) and abs((a["year"] or 0) - (b["year"] or 0)) <= 16
                if link:
                    parent[find(i)] = find(j)
        comp = defaultdict(list)
        for i, r in enumerate(rows):
            comp[find(i)].append(r)
        groups = []
        for grp in comp.values():               # 컴포넌트 내 생년 충돌이면 생년별 재분리
            cdobs = {r["dob"] for r in grp if r.get("dob")}
            if len(cdobs) <= 1:
                groups.append((next(iter(cdobs)) if cdobs else None, grp))
            else:
                gd = defaultdict(list)
                for r in grp:
                    gd[r.get("dob")].append(r)
                groups.extend(gd.items())
        namesake = len(groups) > 1               # 같은 이름이 여러 인물로 갈림 → 동명이인 표시
        for dob, grp in groups:
            grp.sort(key=lambda r: (r.get("date") or str(r["year"] or ""), r["eid"]))
            wins = sum(1 for r in grp if r["won"])
            losses = sum(1 for r in grp if not r["won"])
            parties = []
            seen_p = set()
            for r in grp:
                if r["party"] and r["party"] not in seen_p:
                    seen_p.add(r["party"])
                    parties.append(r["party"])
            persons.append({
                "name": nm,
                "id": f"{nm}-{dob}" if dob else nm,
                "dob": dob,
                "hanja": next((r["hanja"] for r in grp if r.get("hanja")), None),
                "wins": wins, "losses": losses,
                "parties": parties[:6],
                "sidos": sorted(set(s for r in grp for s in r["sidos"])),
                "likely_namesake": namesake,
                "races": [{
                    "eid": r["eid"], "year": r["year"], "round": r["round"], "date": r.get("date"),
                    "place": r["place"], "party": r["party"],
                    "pct": r["pct"], "rank": r["rank"], "won": r["won"],
                    "tc": r["tc"],
                } for r in grp],
            })

    # 인기순 (race 많은 사람 우선)
    persons.sort(key=lambda p: (-len(p["races"]), -p["wins"], p["name"]))

    out = {
        "_meta": {
            "n_persons": len(persons),
            "n_races": sum(len(p["races"]) for p in persons),
            "n_wins_total": sum(p["wins"] for p in persons),
            "description": "이름 기준 cluster — 동명이인 split은 UI에서 처리",
        },
        "persons": persons,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    sz = OUT.stat().st_size
    print(f"→ {OUT.relative_to(ROOT)}: {len(persons)} persons · "
          f"{out['_meta']['n_races']} races · {sz/1024:.1f} KB")
    # top 10 by race count
    print("\n상위 10명 (race 수 기준):")
    for p in persons[:10]:
        flag = " [동명이인?]" if p["likely_namesake"] else ""
        print(f"  {p['name']:8s}  W{p['wins']:2d} L{p['losses']:2d}  "
              f"{len(p['races'])}회{flag}  {' · '.join(p['parties'][:3])}")


if __name__ == "__main__":
    main()
