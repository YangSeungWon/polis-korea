"""data/raw/nesdc_9th_polls.csv + data/raw/parsed/*.json → data/polls/aggregated.json.

각 파싱된 다자대결 문항 1개 = 1 poll 레코드.
hex/시군구 시각화는 이 JSON을 fetch해서 시도·시군구·office 단위로 group.

법적 의무 (project_election_poll_legal 메모):
- 각 레코드에 의뢰자·기관·조사기간·표본수·응답률·표본오차 + source_url 보존
- 의뢰자가 정당·후보자 본인이면 except로 표시 (display 시 필터링 가능)
- 블랙아웃 (2026-05-28 ~ 06-03 18:00) 도래 시 publish_cutoff 적용
"""

from __future__ import annotations
import csv
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
META_CSV = ROOT / "data" / "raw" / "nesdc_9th_polls.csv"
PARSED_DIR = ROOT / "data" / "raw" / "parsed"
OUT_DIR = ROOT / "data" / "polls"
OUT_PATH = OUT_DIR / "aggregated.json"

ELECTION_DATE = date(2026, 6, 3)
BLACKOUT_START = date(2026, 5, 28)  # 5/28 00:00부터 공표 금지
BLACKOUT_END = datetime(2026, 6, 3, 18, 0)  # 6/3 18:00 해제

# 17 시도 캐노니컬 명
SIDO_CANONICAL = {
    "서울": "서울특별시", "서울특별시": "서울특별시",
    "부산": "부산광역시", "부산광역시": "부산광역시",
    "대구": "대구광역시", "대구광역시": "대구광역시",
    "인천": "인천광역시", "인천광역시": "인천광역시",
    "광주": "광주광역시", "광주광역시": "광주광역시",
    "대전": "대전광역시", "대전광역시": "대전광역시",
    "울산": "울산광역시", "울산광역시": "울산광역시",
    "세종": "세종특별자치시", "세종특별자치시": "세종특별자치시",
    "경기": "경기도", "경기도": "경기도",
    "강원": "강원특별자치도", "강원도": "강원특별자치도", "강원특별자치도": "강원특별자치도",
    "충북": "충청북도", "충청북도": "충청북도",
    "충남": "충청남도", "충청남도": "충청남도",
    "전북": "전북특별자치도", "전라북도": "전북특별자치도", "전북특별자치도": "전북특별자치도",
    "전남": "전라남도", "전라남도": "전라남도",
    "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도",
    "제주": "제주특별자치도", "제주특별자치도": "제주특별자치도", "제주도": "제주특별자치도",
}


def canon_sido(s: str) -> str:
    if not s:
        return ""
    return SIDO_CANONICAL.get(s, s)


def parse_region(region: str) -> tuple[str, str]:
    """`region` 필드 → (sido_canonical, sigungu).

    예: "경상북도 구미시" → ("경상북도", "구미시")
        "충청남도" → ("충청남도", "")
        "전라남도 영광군 나선거구" → ("전라남도", "영광군")  # 선거구 표기 제거
    """
    if not region:
        return ("", "")
    # 선거구 부분 제거
    region = re.sub(r"\s+[가-힣]+선거구.*$", "", region.strip())
    parts = region.strip().split()
    if not parts:
        return ("", "")
    sido = canon_sido(parts[0])
    # 첫 sigungu token만 사용 (NESDC가 "OO시 OO도 전체" 식 멀티 region 묶음 가능)
    sigungu = parts[1] if len(parts) > 1 else ""
    # 시도 전체 마커 또는 시도명이 또 나오면 비움
    if sigungu in {"전체", "전 지역", "전지역"} or canon_sido(sigungu) in SIDO_CANONICAL.values():
        sigungu = ""
    return (sido, sigungu)


def classify_office(title: str, sido: str, sigungu: str) -> tuple[str, str]:
    """문항 제목 + 지역 → (office_level, office_label).

    office_level: 광역단체장 / 기초단체장 / 교육감 / 광역의원 / 기초의원 / 비례 / 기타
    office_label: 도지사 / 광역시장 / 특별시장 / 자치구청장 / 시장 / 군수 / 교육감 / ...
    """
    if not title:
        return ("기타", "")

    # 교육감 (광역 단위, 무소속)
    if "교육감" in title:
        return ("교육감", "교육감")

    # 도지사
    if "도지사" in title:
        return ("광역단체장", "도지사")

    # 특별시장·광역시장 — sido가 특별시/광역시이고 "시장" 들어가면
    SPECIAL_SIDOS = {
        "서울특별시": "특별시장",
        "부산광역시": "광역시장",
        "대구광역시": "광역시장",
        "인천광역시": "광역시장",
        "광주광역시": "광역시장",
        "대전광역시": "광역시장",
        "울산광역시": "광역시장",
        "세종특별자치시": "세종시장",
        "제주특별자치도": "도지사",  # 제주는 도지사
    }
    # 시도 short → 광역시장·도지사 매핑 (title이 "인천시장"·"서울시장" 등이면 광역)
    SIDO_SHORT_TO_SIDO = {
        "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
        "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
        "울산": "울산광역시", "세종": "세종특별자치시",
    }
    title_ns = re.sub(r"\s+", "", title)
    # title에 광역시/특별시 시도 short + (광역|특별)?시장 들어가면 광역 (sigungu 있어도)
    # 예: 강화군 PDF "인천시장", 울산 동구 PDF "울산광역시장" → 광역
    for short, sd in SIDO_SHORT_TO_SIDO.items():
        if re.search(rf"{short}(?:특별|광역)?시장", title_ns) and sido == sd:
            return ("광역단체장", SPECIAL_SIDOS.get(sd, "광역시장"))
    if "시장" in title and sido in SPECIAL_SIDOS and not sigungu:
        return ("광역단체장", SPECIAL_SIDOS[sido])

    # 기초단체장
    if "구청장" in title:
        return ("기초단체장", "구청장")
    if "군수" in title:
        return ("기초단체장", "군수")
    if "시장" in title and sigungu:
        return ("기초단체장", "시장")

    return ("기타", "")


def parse_survey_period(s: str) -> tuple[str, str]:
    """`survey_period` 필드에서 시작·종료 ISO 날짜 추출.

    포맷이 일관되지 않음 (단일 날짜 / 범위 / 줄바꿈 포함). 안전하게 두 날짜 찾기.
    """
    if not s:
        return ("", "")
    dates = re.findall(r"(\d{4})[-.]?\s*(\d{1,2})[-.]?\s*(\d{1,2})", s)
    iso = []
    for y, m, d in dates:
        try:
            iso.append(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")
        except ValueError:
            continue
    if not iso:
        return ("", "")
    if len(iso) == 1:
        return (iso[0], iso[0])
    return (iso[0], iso[1])


def to_float(s: str) -> float | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def is_self_poll(requester: str) -> bool:
    """의뢰자가 정당·후보자 본인인지 휴리스틱."""
    if not requester:
        return False
    # "OOO 예비후보", "OOO 후보 선거사무소", "OOO 캠프" 같은 패턴
    if re.search(r"(후보|예비후보|선거사무소|선거대책|캠프|위원회)", requester):
        # 단, 방송사·신문사·언론사 등 매체 키워드가 있으면 자체 조사 아님
        if re.search(r"(방송|신문|언론|미디어|뉴스|일보|MBC|KBS|SBS|JTBC|YTN|TBC)", requester):
            return False
        # 정당 캠프는 의뢰자
        return True
    return False


def load_meta() -> dict[str, dict]:
    if not META_CSV.exists():
        return {}
    with open(META_CSV, newline="", encoding="utf-8") as f:
        return {row["ntt_id"]: row for row in csv.DictReader(f)}


def load_parsed() -> dict[str, dict]:
    """ntt_id → parsed PDF JSON (총 데이터 풍부한 쪽 우선)."""
    by_id: dict[str, dict] = {}
    if not PARSED_DIR.exists():
        return by_id
    for path in PARSED_DIR.glob("*.json"):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        nid = d.get("ntt_id", "")
        if not nid:
            continue
        # 한 ntt_id에 여러 PDF (질문지 + 결과). 데이터 풍부한 쪽 우선.
        def score(jd):
            return sum(
                1
                for q in jd.get("questions", [])
                if q.get("candidates") and any("pct" in c for c in q["candidates"])
            )
        existing = by_id.get(nid)
        if existing is None or score(d) > score(existing):
            by_id[nid] = d
    return by_id


# 표 제목 → metric_type 매핑
def detect_metric_type(title: str, election_office: str) -> str:
    """질문 메타·제목으로부터 metric_type 결정."""
    if election_office == "정당지지":
        return "정당지지"
    if election_office == "국정평가":
        return "국정평가"
    if election_office == "투표의향":
        return "투표의향"
    if election_office == "비례정당":
        return "비례정당"
    # 후보지지 — 세부 분류
    if "당선" in title and ("가능" in title or "예측" in title):
        return "당선가능성"
    if "적합" in title:
        return "적합도"
    return "후보지지"


def build() -> dict:
    meta = load_meta()
    parsed = load_parsed()

    polls = []
    skipped_self = 0
    skipped_no_pdf = 0
    skipped_no_candidates = 0

    canonical_sidos = set(SIDO_CANONICAL.values())
    for ntt_id, m in meta.items():
        sido, sigungu = parse_region(m.get("region", ""))
        # 매핑 안 되는 시도 (전국·해외 등) skip — 시각화 단위 아님
        if sido and sido not in canonical_sidos:
            continue
        # 스크래퍼가 이미 시작·종료 분리해줌; 없으면 raw에서 추출
        period_start = m.get("survey_start", "") or parse_survey_period(m.get("survey_period", ""))[0]
        period_end = m.get("survey_end", "") or parse_survey_period(m.get("survey_period", ""))[1]
        # 역전(메타 start/end 뒤바뀜, 예 5/18~5/17) 교정
        if period_start and period_end and period_start > period_end:
            period_start, period_end = period_end, period_start
        requester = m.get("requester", "")
        self_poll = is_self_poll(requester)

        p = parsed.get(ntt_id)
        if not p:
            skipped_no_pdf += 1
            continue

        # 후보지지·당선가능성·정당지지·국정평가·투표의향 모두 emit
        any_emitted = False
        # 메트릭 응답어 (후보 선택 기준·당선가능성 등) — 가짜 후보 list reject
        METRIC_NAME_KW = {
            '차기후보', '선택기준', '선택이유', '소속정당', '지지정당', '개인의',
            '정책과', '정책능력', '도덕성', '당선가능', '당선가능성', '인지도',
            '리더십', '공약', '경력', '전문성', '이미지', '신뢰성', '추진력',
            '기준이', '이유가', '이유는', '동기는',
            # 추가 — 폴 detail에서 본 케이스
            '이외다른', '당선될', '다른사람', '사람이', '정치현안', '현안',
            '지지정당', '지지후보', '투표예정', '투표할', '없음', '없다',
            '모름', '무응답', '기타', '기타후보',
            # 2자 응답/통계 토큰
            '다른', '모르', '거절', '완료', '합계', '중에', '경우',
            '보수', '중도', '진보', '성향',
        }
        # 후보 이름에 들어있으면 그 record가 OCR 오류·메트릭 표일 가능성 높음
        BAD_NAME_PATTERNS = re.compile(
            r'(정읍|위원회|수석|비서|현안|지지|의장|회장|당선|기관|단체|기타|모름|무응답)'
        )
        for q in p.get("questions", []):
            cands = q.get("candidates") or []
            if not cands or not any("pct" in c for c in cands):
                continue
            # 후보 이름에 metric keyword가 하나라도 있으면 그 question reject (메트릭 표를 후보로 오인)
            names = [c.get("name", "") for c in cands]
            names_clean = [re.sub(r"\s+", "", n) for n in names]
            if any(n in METRIC_NAME_KW for n in names_clean):
                continue
            # 후보 이름에 지명·직책·기관 keyword (BAD_NAME_PATTERNS) 포함이면 reject
            if any(BAD_NAME_PATTERNS.search(n) for n in names_clean):
                continue
            # 동일 이름 반복 (parse 시 column 인식 실패 → 한 이름이 전 후보 자리 채움)
            non_empty = [n for n in names_clean if n]
            if len(non_empty) >= 3 and len(set(non_empty)) < len(non_empty) * 0.6:
                continue
            election_office = q.get("election_office", "")
            title = q.get("title", "")
            metric_type = detect_metric_type(title, election_office)

            # 합계 정규화 + 비정상 필터
            pcts = [c.get("pct") for c in cands if c.get("pct") is not None]
            if pcts:
                s = sum(pcts)
                # 1) 1000 단위 양식 (단위:0.1%) → /10
                if 700 <= s <= 1100:
                    for c in cands:
                        if c.get("pct") is not None:
                            c["pct"] = round(c["pct"] / 10, 1)
                    s = s / 10
                # 2) 합계 0 또는 너무 큼 → 추출 실패, skip
                if s == 0 or s > 110:
                    continue
            # 찬반 표 잘못 분류 (e.g., "약속하는 후보 지지") → skip
            if metric_type in ("후보지지", "당선가능성") and re.search(r"찬\s*성|반\s*대|폐\s*지|약속하는|찬반", title):
                continue
            # 후보지지·당선가능성·적합도만 office_level 분류, 나머지는 광역/시도 단위 메트릭
            if metric_type in ("후보지지", "당선가능성", "적합도"):
                office_level, office_label = classify_office(title, sido, sigungu)
            else:
                # 정당지지·국정평가·투표의향 — sido(+sigungu) 단위, office_level은 메트릭 자체
                office_level = metric_type
                office_label = metric_type
            polls.append({
                "ntt_id": ntt_id,
                "source_url": m.get("source_url", ""),
                "agency": m.get("agency", ""),
                "co_agency": m.get("co_agency", ""),
                "requester": requester,
                "is_self_poll": self_poll,
                "method": m.get("method", ""),
                "sample_size": to_float(m.get("sample_size", "")),
                "response_rate": to_float(m.get("response_rate", "")),
                "contact_rate": to_float(m.get("contact_rate", "")),
                "sample_error": m.get("sample_error", ""),
                "period_start": period_start,
                "period_end": period_end,
                "reg_date": m.get("reg_date", ""),
                "sido": sido,
                "sigungu": sigungu,
                "office_level": office_level,
                "office_label": office_label,
                "metric_type": metric_type,
                "table_no": q.get("table_no", ""),
                "table_title": title,
                "candidates": [
                    {"name": c.get("name", ""), "party": c.get("party", ""), "pct": c.get("pct")}
                    for c in cands
                    if "pct" in c
                ],
            })
            any_emitted = True

        if not any_emitted:
            skipped_no_candidates += 1

    # OCR / multi-line parsing 오류 보정 — (sido, sigungu, office, 정당)별로 자주 등장하는 후보명을 canonical로.
    # 같은 시군구·정당이면 같은 후보일 가능성 매우 높음. 시도까지만 묶으면 다른 시군구 후보로 잘못 매핑됨
    # (예: 양산 '나동연'이 거창 후보들을 다 덮어버린 사건).
    from collections import Counter, defaultdict
    norm_key_names: dict[tuple[str, str, str, str], Counter] = defaultdict(Counter)
    def _nkey(p):
        return (p["sido"], p.get("sigungu", "") or "", p["office_level"])
    for p in polls:
        if p["metric_type"] not in ("후보지지", "당선가능성", "적합도"):
            continue
        sk = _nkey(p)
        for c in p["candidates"]:
            party = c.get("party", "")
            name = c.get("name", "")
            if not party or not name: continue
            norm_key_names[(*sk, party)][name] += 1
    n_normalized = 0
    for p in polls:
        if p["metric_type"] not in ("후보지지", "당선가능성", "적합도"):
            continue
        sk = _nkey(p)
        for c in p["candidates"]:
            party = c.get("party", "")
            name = c.get("name", "")
            if not party or not name: continue
            counter = norm_key_names[(*sk, party)]
            if counter[name] >= 3: continue
            top = counter.most_common(1)
            if not top: continue
            canonical, top_cnt = top[0]
            if canonical == name or top_cnt < 3: continue
            c["_original_name"] = name
            c["name"] = canonical
            n_normalized += 1
    print(f"  후보명 normalize {n_normalized}건 (OCR/parsing 오류 → canonical)", file=sys.stderr)

    # normalize 후 한 record에서 동일 이름이 비정상적으로 반복되면 (parse 시 column 인식 실패)
    # 그 record의 candidates를 전부 비워서 skip되게 함 — 잘못된 normalize 결과도 정리
    polls_clean = []
    n_dropped_dup = 0
    for p in polls:
        cs = p.get("candidates") or []
        names = [c.get("name", "") for c in cs if c.get("name")]
        if len(names) >= 3 and len(set(names)) < len(names) * 0.6:
            n_dropped_dup += 1
            continue
        polls_clean.append(p)
    polls = polls_clean
    if n_dropped_dup:
        print(f"  중복 이름 record drop {n_dropped_dup}건", file=sys.stderr)

    # 후보명이 정당명·메트릭 라벨인 candidate 제거 ("더불어민주당", "차기동해" 등)
    try:
        from parse_pdf import PARTY_NAMES as _PARTY_NAMES
    except ImportError:
        _PARTY_NAMES = []
    party_name_set = {re.sub(r"\s+", "", p) for p in _PARTY_NAMES}
    metric_in_name = re.compile(r'^(차기|적합|선호|지지|당선|소속|예정|성향|진영)')
    n_candrm = 0
    for p in polls:
        keep = []
        for c in p.get("candidates", []):
            nm = re.sub(r"\s+", "", c.get("name", ""))
            if not nm:
                keep.append(c); continue
            if nm in party_name_set:
                n_candrm += 1; continue
            if metric_in_name.search(nm):
                n_candrm += 1; continue
            keep.append(c)
        p["candidates"] = keep
    if n_candrm:
        print(f"  정당명·메트릭 라벨 candidate 제거 {n_candrm}건", file=sys.stderr)

    # 한 record 안 동일 name 후보 dedup (pct 큰 쪽 유지)
    n_dup_in = 0
    for p in polls:
        seen = {}
        for c in p.get("candidates", []):
            nm = c.get("name", "")
            if not nm:
                seen.setdefault("", c); continue
            cur = seen.get(nm)
            if cur is None or (c.get("pct") or 0) > (cur.get("pct") or 0):
                if cur is not None: n_dup_in += 1
                seen[nm] = c
            else:
                n_dup_in += 1
        p["candidates"] = list(seen.values())
    if n_dup_in:
        print(f"  record 내 동일 name dedup {n_dup_in}건", file=sys.stderr)

    # 같은 (ntt_id, office_level, sido, sigungu, table_title) records merge — 한 표 split 복구
    groups = defaultdict(list)
    for p in polls:
        key = (p["ntt_id"], p.get("office_level", ""), p.get("sido", ""),
               p.get("sigungu", "") or "", p.get("table_title", ""))
        groups[key].append(p)
    merged = []
    n_merged = 0
    for key, ps in groups.items():
        if len(ps) == 1:
            merged.append(ps[0]); continue
        base = ps[0]
        cands = {}
        for q in ps:
            for c in q.get("candidates", []):
                nm = c.get("name", "")
                if not nm: continue
                cur = cands.get(nm)
                if cur is None or (c.get("pct") or 0) > (cur.get("pct") or 0):
                    cands[nm] = c
        base["candidates"] = list(cands.values())
        merged.append(base)
        n_merged += len(ps) - 1
    polls = merged
    if n_merged:
        print(f"  같은 표 split records merge {n_merged}건 흡수", file=sys.stderr)

    # candidates 비어버린 record drop
    polls = [p for p in polls if p.get("candidates")]

    # 후보 → 정당 자동 매핑 (정당 미표기 양식 fix)
    # 정당이 있는 후보들에서 (sido, name) → party 사전 구축, 시도·전국 우선순위
    name_party_by_sido: dict[tuple[str, str], dict[str, int]] = {}
    name_party_global: dict[str, dict[str, int]] = {}
    for p in polls:
        if p["metric_type"] not in ("후보지지", "당선가능성", "적합도"):
            continue
        for c in p["candidates"]:
            name = c.get("name", "")
            party = c.get("party", "")
            if not name or not party:
                continue
            sido = p.get("sido", "")
            k_sido = (sido, name)
            d_sido = name_party_by_sido.setdefault(k_sido, {})
            d_sido[party] = d_sido.get(party, 0) + 1
            d_glob = name_party_global.setdefault(name, {})
            d_glob[party] = d_glob.get(party, 0) + 1

    def majority(party_counts: dict[str, int]) -> str:
        return max(party_counts.items(), key=lambda x: x[1])[0] if party_counts else ""

    # NEC 후보자 통합검색 캐시 (조사에 정당 한 번도 안 적힌 후보 보완용)
    # backfill_candidate_party.py 산출. "sido|name" → 공식 정당.
    cand_party_cache = {}
    _cp = ROOT / "data" / "raw" / "nec_candidate_party.json"
    if _cp.exists():
        try:
            cand_party_cache = json.loads(_cp.read_text(encoding="utf-8"))
        except Exception:
            cand_party_cache = {}

    # 정당 빈 후보에 mapping 적용 (다수결 → NEC 캐시 순)
    n_party_filled = n_party_nec = 0
    for p in polls:
        if p["metric_type"] not in ("후보지지", "당선가능성", "적합도"):
            continue
        sido = p.get("sido", "")
        for c in p["candidates"]:
            if c.get("party"):
                continue
            name = c.get("name", "")
            if not name:
                continue
            party = ""
            k_sido = (sido, name)
            if k_sido in name_party_by_sido:
                party = majority(name_party_by_sido[k_sido])
            elif name in name_party_global:
                party = majority(name_party_global[name])
            if party:
                c["party"] = party
                n_party_filled += 1
            elif cand_party_cache.get(f"{sido}|{name}"):  # NEC 공식 정당 보완
                c["party"] = cand_party_cache[f"{sido}|{name}"]
                n_party_nec += 1
    if n_party_nec:
        print(f"  NEC 후보자검색으로 정당 보완: {n_party_nec}건")

    # 중복 카드 제거 — 같은 등록(ntt_id)·office·지역의 동일 후보집합은 보통 지역별/페이지
    # cross-tab 분해라 전체 1건만 남긴다. 양자대결 등 다른 후보집합은 키가 달라 보존.
    # 표본 큰 것(=전체) 우선, 동률이면 후보 많은 것.
    seen_card: dict[tuple, int] = {}
    deduped = []
    n_dup = 0
    for p in polls:
        names = tuple(sorted(c.get("name", "") for c in p.get("candidates", [])))
        k = (p.get("ntt_id"), p["office_level"], p.get("sido", ""), p.get("sigungu", ""), names)
        if k not in seen_card:
            seen_card[k] = len(deduped)
            deduped.append(p)
            continue
        n_dup += 1
        idx = seen_card[k]
        prev = deduped[idx]
        score = lambda q: ((q.get("sample_size") or 0), len(q.get("candidates", [])))
        if score(p) > score(prev):
            deduped[idx] = p
    if n_dup:
        print(f"  중복 카드 제거: {n_dup}건 ({len(polls)}→{len(deduped)})")
    polls = deduped

    # 블랙아웃 판정 (build 실행 시각 기준)
    now = datetime.now()
    blackout_active = BLACKOUT_START <= now.date() <= BLACKOUT_END.date()
    if blackout_active and now.date() == BLACKOUT_END.date() and now.hour >= 18:
        blackout_active = False

    out = {
        "_meta": {
            "generated_at": now.isoformat(timespec="seconds"),
            "election_date": ELECTION_DATE.isoformat(),
            "blackout_start": BLACKOUT_START.isoformat(),
            "blackout_end": BLACKOUT_END.isoformat(timespec="minutes"),
            "blackout_active": blackout_active,
            "source": "NESDC 등록현황 (nesdc.go.kr)",
            "legal_notice": "본 자료는 NESDC 등록 조사 인용. 인용 시 의뢰자·기관·조사기간·표본수·응답률·표본오차 표시 의무.",
            "stats": {
                "total_polls_meta": len(meta),
                "matched_parsed": sum(1 for m in meta if m in parsed),
                "emitted_records": len(polls),
                "skipped_no_pdf": skipped_no_pdf,
                "skipped_no_candidates": skipped_no_candidates,
            },
        },
        "polls": polls,
    }
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = build()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    meta = out["_meta"]["stats"]
    print(f"메타 {meta['total_polls_meta']}건, 파싱 매칭 {meta['matched_parsed']}건, "
          f"emit {meta['emitted_records']}개", file=sys.stderr)
    print(f"  skip(PDF없음) {meta['skipped_no_pdf']}, skip(후보없음) {meta['skipped_no_candidates']}",
          file=sys.stderr)
    print(f"→ {OUT_PATH.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
