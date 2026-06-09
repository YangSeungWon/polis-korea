"""국회 역대 의원 데이터(assembly_member_map)로 person-index의 국회의원 row를
unique ID로 매칭. 매칭은 이름 + 회차 N + 지역구 keyword 기반.

Output: assets/person-index.json (덮어씀) — 각 race에 assembly_id 필드 추가.
race가 assembly_id를 가지면 person.js가 그것 기준으로 cluster (동명이인 정확 분리).

매칭 정책:
1. 우리 데이터의 (eid=Nth-general-YYYY, name) → assembly persons 후보 추출
   (assembly person의 careers 중 n==N 이고 name 일치한 case)
2. district keyword (시도 약어·시군구 명) overlap으로 disambig
3. 정확 1명 → assembly_id 부여. 0/2+명 → 매칭 없음.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERSON_IDX = ROOT / "assets/person-index.json"
ASSEMBLY_MAP = ROOT / "data/raw/assembly_member_map.json"


def normalize_district(s: str) -> str:
    """공백·시·구 같은 일반 토큰 제거 → 핵심 키워드만."""
    s = s or ""
    s = re.sub(r"\s+", "", s)
    # 시도 prefix는 우리 데이터에서 별도로 sido 필드에 있어 빠질 수 있음 — 양쪽에서 동등 처리.
    return s


def eid_to_assembly_n(eid: str) -> int | None:
    """13th-general-1988 → 13."""
    m = re.match(r"(\d+)(?:st|nd|rd|th)-general-", eid)
    return int(m.group(1)) if m else None


def main():
    person = json.loads(PERSON_IDX.read_text(encoding="utf-8"))
    asm = json.loads(ASSEMBLY_MAP.read_text(encoding="utf-8"))

    # name → 후보 assembly persons list (회차별 careers와 함께)
    by_name = {}
    for p in asm["persons"]:
        nm = p["name"]
        by_name.setdefault(nm, []).append(p)

    n_matched = 0
    n_ambig = 0
    n_total_general = 0
    # 적용
    for person_entry in person["persons"]:
        nm = person_entry["name"]
        candidates_for_name = by_name.get(nm, [])
        for race in person_entry["races"]:
            # 총선만 매핑 (assembly는 국회의원 한정)
            n = eid_to_assembly_n(race["eid"])
            if n is None:
                continue
            n_total_general += 1
            # 후보 — careers에 (n=N, name=nm) 있는 person들
            possible = []
            for asm_p in candidates_for_name:
                for c in asm_p["careers"]:
                    if c["n"] != n:
                        continue
                    possible.append((asm_p, c))
            if not possible:
                continue
            if len(possible) == 1:
                race["assembly_id"] = possible[0][0]["id"]
                n_matched += 1
                continue
            # 다수 — 지역구 keyword overlap으로 분리
            our_place = normalize_district(race.get("place", ""))
            best = []
            for asm_p, c in possible:
                their = normalize_district(c["district"])
                # 양쪽이 비례면 그대로 매치
                if "비례" in our_place and "비례" in their:
                    best.append(asm_p)
                    continue
                # substring overlap 충분?
                if their and our_place and (their in our_place or our_place in their
                        or any(t for t in their.replace("시", " ").replace("구", " ").split() if t and t in our_place)):
                    best.append(asm_p)
            if len(best) == 1:
                race["assembly_id"] = best[0]["id"]
                n_matched += 1
            elif len(best) >= 2:
                n_ambig += 1

    person["_meta"]["assembly_matched"] = n_matched
    person["_meta"]["assembly_ambiguous"] = n_ambig
    person["_meta"]["assembly_total_general"] = n_total_general

    # 재cluster — assembly_id 있으면 그걸 기준으로 인물 분리/통합.
    # unassigned race는 sido overlap으로 가장 가까운 assembly 그룹에 attach.
    asm_lookup = {p["id"]: p for p in asm["persons"]}

    def race_sido(r):
        place = r.get("place", "") or ""
        sido = r.get("sido", "") or ""
        # place 앞 토큰에서 시도명 후보
        m = re.match(r"^([가-힣]+(?:특별시|광역시|특별자치시|특별자치도|도))", place)
        return sido or (m.group(1) if m else "") or place[:2]

    # '전국구'·'비례대표' 같은 시스템 토큰은 지리 매칭 제외 — 무관 race 잘못 끌어붙음.
    SYSTEM_TOKENS = {"전국", "전국구", "비례", "비례대표"}

    def career_sido_tokens(career_district):
        """career district에서 시도/지명 토큰 집합 — 부분 매칭용."""
        # "경남 창원시성산구" → {"경남","창원","성산"}
        tokens = set()
        for t in re.split(r"\s+", career_district or ""):
            if t:
                if t not in SYSTEM_TOKENS:
                    tokens.add(t)
                # 시군구 prefix
                for sub in re.findall(r"[가-힣]+?(?:시|군|구)", t):
                    stripped = sub.rstrip("시군구")
                    if stripped not in SYSTEM_TOKENS:
                        tokens.add(stripped)
                    if sub not in SYSTEM_TOKENS:
                        tokens.add(sub)
        return tokens

    PARTY_FAMILY = {
        "통일민주당": "M", "민주당": "M", "새정치국민회의": "M", "새천년민주당": "M",
        "열린우리당": "M", "민주통합당": "M", "새정치민주연합": "M", "더불어민주당": "M",
        "더불어민주연합": "M", "통합민주당": "M", "열린민주당": "M",
        "새로운미래": "M", "조국혁신당": "M",  # 민주 분당계열
        "민주자유당": "C", "신한국당": "C", "한나라당": "C", "새누리당": "C",
        "자유한국당": "C", "미래통합당": "C", "국민의힘": "C", "국민의미래": "C",
        "자유선진당": "C",
    }

    def aid_score(aid, race, race_group_parties, group_years):
        """unassigned race와 aid 그룹의 attach score.
        sido/place overlap + 정당 패밀리 match/mismatch + 시간 근접도.
        """
        asm_p = asm_lookup.get(aid)
        if not asm_p:
            return 0
        rs = race_sido(race)
        rplace = (race.get("place") or "").replace(" ", "")
        score = 0
        for c in asm_p["careers"]:
            tokens = career_sido_tokens(c["district"])
            for tk in tokens:
                if not tk:
                    continue
                if rs and (tk in rs or rs in tk):
                    score += 2
                if tk in rplace or rplace in tk:
                    score += 1
        # 정당 패밀리 — race·group 동일이면 +3, 다르면 -4 (동명이인 차단).
        r_fam = PARTY_FAMILY.get(race.get("party") or "")
        if r_fam:
            if r_fam in race_group_parties:
                score += 3
            elif race_group_parties:
                score -= 4
        # 시간 근접도 — race 연도와 group 회차 연도 차.
        r_year = race.get("year")
        if r_year and group_years:
            min_gap = min(abs(r_year - y) for y in group_years)
            if min_gap <= 5:
                score += 2
            elif min_gap >= 30:
                score -= 5  # 30년+ 격차는 다른 사람일 가능성 큼
        return score

    new_persons = []
    for entry in person["persons"]:
        groups: dict = {}
        unassigned = []
        for r in entry["races"]:
            aid = r.get("assembly_id")
            if aid:
                groups.setdefault(aid, []).append(r)
            else:
                unassigned.append(r)
        if not groups:
            new_persons.append(entry)
            continue
        # unassigned를 attach score 높은 aid 그룹에 attach. 0 이하면 orphan.
        group_families = {
            aid: {PARTY_FAMILY.get(r.get("party") or "") for r in races if r.get("party")}
            for aid, races in groups.items()
        }
        # 그룹별 연도 셋 (시간 근접도 산정용)
        group_years = {
            aid: {r.get("year") for r in races if r.get("year")}
            for aid, races in groups.items()
        }
        orphans = []
        for r in unassigned:
            best_aid = None
            best_score = 0
            for aid in groups:
                s = aid_score(aid, r, group_families.get(aid, set()), group_years.get(aid, set()))
                if s > best_score:
                    best_score = s
                    best_aid = aid
            if best_aid and best_score >= 2:
                groups[best_aid].append(r)
            else:
                orphans.append(r)
        # 한 그룹 + orphan = 그대로 entry로 유지 (단일 인물 + 일부 매칭 안된 race)
        if len(groups) == 1 and not orphans:
            aid = next(iter(groups))
            asm_person = asm_lookup.get(aid)
            entry["assembly_id"] = aid
            entry["hanja"] = asm_person.get("hanja") if asm_person else None
            entry["dob"] = asm_person.get("dob") if asm_person else None
            entry["races"] = groups[aid]
            entry["wins"] = sum(1 for r in entry["races"] if r["won"])
            entry["losses"] = sum(1 for r in entry["races"] if not r["won"])
            new_persons.append(entry)
            continue
        # split — 각 group + orphan 별도
        for aid, races in groups.items():
            asm_person = asm_lookup.get(aid)
            sub = dict(entry)
            sub["id"] = aid
            sub["assembly_id"] = aid
            sub["hanja"] = asm_person.get("hanja") if asm_person else None
            sub["dob"] = asm_person.get("dob") if asm_person else None
            sub["races"] = races
            sub["wins"] = sum(1 for r in races if r["won"])
            sub["losses"] = sum(1 for r in races if not r["won"])
            sub["likely_namesake"] = False
            seen_p = set(); parties = []
            for r in races:
                if r["party"] and r["party"] not in seen_p:
                    seen_p.add(r["party"]); parties.append(r["party"])
            sub["parties"] = parties[:6]
            new_persons.append(sub)
        if orphans:
            tail = dict(entry)
            tail["id"] = entry["id"] + "_unmatched"
            tail["races"] = orphans
            tail["wins"] = sum(1 for r in orphans if r["won"])
            tail["losses"] = sum(1 for r in orphans if not r["won"])
            tail.pop("assembly_id", None)
            new_persons.append(tail)

    new_persons.sort(key=lambda p: (-len(p["races"]), -p.get("wins", 0), p["name"]))
    person["persons"] = new_persons
    person["_meta"]["n_persons"] = len(new_persons)

    PERSON_IDX.write_text(json.dumps(person, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    sz = PERSON_IDX.stat().st_size
    print(f"→ {PERSON_IDX.relative_to(ROOT)}: {len(new_persons)} persons · {sz/1024:.1f} KB")
    print(f"  총선 race 중 assembly 매칭: {n_matched} · 모호: {n_ambig} · 총선 race total: {n_total_general}")


if __name__ == "__main__":
    main()
