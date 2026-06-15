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


def hanja_variant(a, b):
    """두 한자명이 표기 변이체인가 — 같은 길이 + ≤1글자 차이(勳 U+52F3 / 勲 U+52F2 등).
    NEC가 동일인 한자를 회차마다 변이체로 주므로, 같은 생일이면 이를 동일인으로 본다.
    HTML 엔티티(&#NNN;)는 1글자로 정규화 후 비교. 둘 다 있을 때만 판정(미상은 호출측 처리)."""
    if not a or not b:
        return False
    a2 = re.sub(r"&#\d+;", "?", a)
    b2 = re.sub(r"&#\d+;", "?", b)
    if len(a2) != len(b2):
        return False
    return sum(1 for x, y in zip(a2, b2) if x != y) <= 1


_PROV_PREFIX = re.compile(
    r"^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)\s")


def dist_core(s):
    """선거구/지역구 문자열 → 핵심 지명 토큰 집합.

    MONA('충남 아산', '경기 인천갑')와 결과('아산군', '인천시 갑', '제3선거구(천안시·아산군)')의
    표기차를 흡수: 맨 앞 도(道) 접두 제거 + '제N선거구' 래퍼·괄호·구분자 제거 + 시/군/구/읍/면 및
    분구(갑·을·병·정) 접미 제거. 1글자 토큰(중·서 등)은 모호해 제외."""
    if not s:
        return set()
    s = re.sub(r"제\d+선거구", " ", s)
    s = re.sub(r"[()]", " ", s)
    s = _PROV_PREFIX.sub("", s.strip())
    s = re.sub(r"[·,，、\s]+", " ", s).strip()
    toks = set()
    for t in s.split(" "):
        t = re.sub(r"(시|군|구|읍|면|동)$", "", t)
        t = re.sub(r"(갑|을|병|정)$", "", t)
        if len(t) >= 2:
            toks.add(t)
    return toks


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

    def match_assembly(name, eid, place, won):
        """총선 race → assembly_map(이름+회차+지역구)로 (dob, 한자). 비의원·미매칭이면 (None, None).

        지역구 일치를 우선 — 같은 회차에 동명 의원이 1명뿐이어도 지역구가 다르면(같은 이름의
        낙선자) 그 의원으로 보지 않는다. 옛 의원 dob가 같은 회차 타지역구 낙선자에게 잘못
        퍼지던 것 차단(이상철 1893 → 개풍·부산·청양에 모두 부여되던 버그). 단 당선자이고
        동명 의원이 1명뿐이면 지역구 표기차를 보정해 그 사람으로 인정."""
        m = re.match(r"(\d+)(?:st|nd|rd|th)-general-", eid)
        if not m:
            return None, None
        recs = asm_careers.get((name, int(m.group(1))))
        if not recs:
            return None, None
        p = _nm(place)
        pcore = dist_core(place)
        for dob, hanja, dist in recs:  # 동명 의원 — 지역구로 분별
            d = _nm(dist)
            if p and d and (d in p or p in d):
                return dob, hanja
            if pcore and dist_core(dist) & pcore:   # 핵심 지명 토큰 일치(표기차 흡수)
                return dob, hanja
        if won and len(recs) == 1:     # 당선자 + 동명 의원 1명 → 지역구 표기차 보정
            return recs[0][0], recs[0][1]
        return None, None

    # 수동 백필(manual_bio) — NEC·MONA 미보유 당선자(옛 대통령·1995/1998 단체장 등).
    # match={eid,place,tc}로 정확한 race에 귀속. bio·assembly가 못 채울 때만 폴백.
    manual_bio = {}
    man_path = ROOT / "data/manual_bio.json"
    if man_path.exists():
        for r in json.loads(man_path.read_text(encoding="utf-8")).get("records", []):
            mt = r.get("match", {})
            manual_bio[(r["name"], mt.get("eid"), mt.get("place"), str(mt.get("tc")))] = (
                r.get("dob") or None, r.get("hanja") or None)

    def match_manual(name, eid, place, tc):
        return manual_bio.get((name, eid, place, str(tc)), (None, None))

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
                    adob, ahanja = match_assembly(nm, eid, place, won)
                    dob = dob or adob
                    hanja = hanja or ahanja
                if not dob or not hanja:                    # 수동 백필(옛 대통령·1995/1998 단체장 등)
                    mdob, mhanja = match_manual(nm, eid, place, tc)
                    dob = dob or mdob
                    hanja = hanja or mhanja
                # 키에 sido+place(지역구) 포함 — 같은 선거·같은 정당이라도 다른 지역구면 다른 사람.
                #   (옛 총선 동명이인이 한 행으로 뭉쳐 도(道)를 가로질러 잘못 병합되던 것 차단.
                #    sido까지 넣어 '중구(서울) vs 중구(부산)' 동음 지역구 교차병합도 방지)
                per_eid[eid][(nm, party, sido, place)].append({
                    "sido": sido, "place": place, "tc": tc,
                    "rank": rank, "won": won,
                    "pct": c.get("pct"), "votes": votes,
                    "dob": dob, "hanja": hanja,
                })

    # 2단계: per (eid, name, party, sido, place) → 1건으로 통합 (최다득표 row 기준)
    flat = []
    for eid, by_np in per_eid.items():
        m = eid_meta.get(eid, {})
        for (nm, party, _sido, _place), rows in by_np.items():
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
        # 동명이인 분리 — union-find. 생년월일이 둘 다 있으면 dob가 결정적(같으면 동일인,
        # 다르면 타인) — NEC 한자는 같은 사람도 회차마다 변이체(勳 U+52F3 / 勲 U+52F2)로 와
        # 한자 비교만으론 동일인이 쪼개짐. dob 미상 측은 한자(있으면) 일치, 둘 다 미상이면
        # 같은 시도 + 가까운 연도(≤16년)로 군집(옛 선거 낙선자). 다른 한자/연도는 병합 금지.
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
                if da and db:
                    # 둘 다 dob 있으면 dob가 결정적 — 같은 이름+정확히 같은 생년월일은 사실상
                    # 동일인(NEC 한자는 같은 사람도 회차마다 다르게 기록: 나경원 羅卿瑗/羅景垣 등).
                    link = da == db
                elif (a["tc"] == "4" and b["tc"] == "4"
                      and a["place"] and a["place"] == b["place"]):
                    # 같은 시군구 단체장(tc4) + 동명 → 동일인(재선/복귀). 연도·소스공백(1995/1998
                    # 무dob) 무관 강링크 — 같은 군수/시장 자리가 둘로 갈리던 것 복원.
                    link = True
                else:
                    # dob 미상 — 같은 지역에서만 동일인 추정(다른 도 연쇄 차단: 이상철 李相喆 등).
                    #   옛 선거는 sido가 'None'으로 비어 모두 같은 시도로 오인되므로, 빈 시도는
                    #   지역구명(place)을 지역 토큰으로 폴백해 도(道)를 가로지른 병합을 막는다.
                    ra = {s for s in a["sidos"] if s and s != "None"} or {a.get("place", "")}
                    rb = {s for s in b["sidos"] if s and s != "None"} or {b.get("place", "")}
                    if not (ra & rb):
                        continue
                    # 같은 지역 안: 한자 둘 다 있고 '진짜' 다르면 타인. 아니면 한자일치/변이체
                    #   또는 가까운 연도(≤16)로 동일인 추정.
                    if ha and hb and ha != hb and not hanja_variant(ha, hb):
                        continue
                    link = (bool(ha and hb and (ha == hb or hanja_variant(ha, hb)))
                            or abs((a["year"] or 0) - (b["year"] or 0)) <= 16)
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
                # 무dob 행(예: 1995/1998 지선 — NEC bio 공백)은 별도 그룹으로 버리지 말고,
                # '같은 지역구(place)' race를 가진 dob 그룹이 유일하면 그쪽에 귀속(같은 단체장이
                # 소스 공백으로 분리되던 것 복원). 같은 연도 충돌(타인)이거나 후보 dob 그룹이
                # 둘 이상이면 안전하게 무dob 그룹 유지.
                none_rows = gd.pop(None, [])
                place_owner = defaultdict(set)
                for d, rs in gd.items():
                    for r in rs:
                        place_owner[r["place"]].add(d)
                leftover = []
                for r in none_rows:
                    owners = place_owner.get(r["place"])
                    if owners and len(owners) == 1:
                        d = next(iter(owners))
                        if not any(x["place"] == r["place"] and x["year"] == r["year"]
                                   for x in gd[d]):
                            gd[d].append(r)
                            continue
                    leftover.append(r)
                groups.extend(gd.items())
                if leftover:
                    groups.append((None, leftover))
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
