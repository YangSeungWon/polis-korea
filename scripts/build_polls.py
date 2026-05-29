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
NEC_ROSTER_PATH = ROOT / "data" / "raw" / "nec_roster_9th.json"

# NEC 9회 지선 등록 후보 명부 — office 재분류·정당 보완에 사용
_NEC_ROSTER: dict = {}
if NEC_ROSTER_PATH.exists():
    try:
        _NEC_ROSTER = json.load(open(NEC_ROSTER_PATH, encoding="utf-8"))
    except Exception:
        _NEC_ROSTER = {}

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


def parse_region(region: str, sub_election: str = "") -> tuple[str, str]:
    """`region` 필드 → (sido_canonical, sigungu).

    예: "경상북도 구미시" → ("경상북도", "구미시")
        "충청남도" → ("충청남도", "")
        "전라남도 영광군 나선거구" → ("전라남도", "영광군")  # 선거구 표기 제거

    region이 시도만이면 sub_election에서 시군구 보강 (19316 'sub_election'에
    "(충청남도 서천군 ...)" 패턴 있는 경우).
    """
    if not region:
        return ("", "")
    region = re.sub(r"\s+[가-힣]+선거구.*$", "", region.strip())
    parts = region.strip().split()
    if not parts:
        return ("", "")
    sido = canon_sido(parts[0])
    sigungu = parts[1] if len(parts) > 1 else ""
    if sigungu in {"전체", "전 지역", "전지역"} or canon_sido(sigungu) in SIDO_CANONICAL.values():
        sigungu = ""
    # sub_election에서 시군구 보강 (NESDC region이 시도만일 때)
    if not sigungu and sub_election and sido:
        # "(충청남도 서천군 기초의원선거 ...)" 패턴에서 sido 직후 한글+(시|군|구) 추출
        m = re.search(rf"{re.escape(sido)}\s+([가-힣]+(?:시|군|구))", sub_election)
        if m:
            cand = m.group(1)
            if canon_sido(cand) not in SIDO_CANONICAL.values():
                sigungu = cand
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

    # title에 "구청장"/"군수"/"시장" 키워드는 없지만 sigungu가 있으면 단위 추정
    # (예: "OO 지방선거 여론조사" — title이 일반화돼있고 표는 구청장 표)
    if sigungu:
        if sido in SPECIAL_SIDOS:  # 광역시·특별시 산하 sigungu = 자치구청장
            return ("기초단체장", "구청장")
        if sigungu.endswith("군"):
            return ("기초단체장", "군수")
        if sigungu.endswith("시"):
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
        sido, sigungu = parse_region(m.get("region", ""), m.get("sub_election", ""))
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
            r'(정읍|위원회|수석|비서|현안|지지|의장|회장|당선|기관|단체|기타|모름|무응답|'
            r'교육청|교육감|교육|자치도|치도|특별시|광역시|협의회|'
            r'행정경험|인지도|경험|능력|이미지|평가|선호도|적합도|'
            r'전교조|노조|조합|것이|이다)'
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
            # 후보 이름에 지명·직책·기관 keyword (BAD_NAME_PATTERNS) 매칭된 candidate만 제거.
            # 정상 후보 1+ 같이 있으면 race 살림 (전체 reject는 너무 aggressive).
            if any(BAD_NAME_PATTERNS.search(n) for n in names_clean):
                cands = [c for c, n in zip(cands, names_clean) if not BAD_NAME_PATTERNS.search(n)]
                names_clean = [n for n in names_clean if not BAD_NAME_PATTERNS.search(n)]
                if not cands:
                    continue
                q["candidates"] = cands  # 정리된 cands 다시 q에 (이후 처리에 사용)
            # 동일 이름 반복 (parse 시 column 인식 실패 → 한 이름이 전 후보 자리 채움)
            non_empty = [n for n in names_clean if n]
            if len(non_empty) >= 3 and len(set(non_empty)) < len(non_empty) * 0.6:
                continue
            election_office = q.get("election_office", "")
            title = q.get("title", "")
            metric_type = detect_metric_type(title, election_office)

            # 적합도 제외 — 경선·예비후보 비교(같은 당 주자 적합도)라 본선 race가 아니다.
            # 정당 모호함(예: 김관영 무소속 vs 민주 경선)·파싱 노이즈의 주범. 본선 후보지지·
            # 정당지지 매치업 시계열만 남긴다.
            # 국정평가·투표의향 — 지선 스코프(VT026)엔 진짜 데이터가 없고, 우리가 가진 건
            # 전부 후보지지 오분류(대부분 중복) + 응답노이즈(것이다·최고위원)라 함께 제외.
            if metric_type in ("적합도", "국정평가", "투표의향"):
                continue
            # 광역의원·기초의원·교육의원 — 시스템 scope 외 (광역단체장·기초단체장·교육감만 카드).
            if election_office in ("광역의원후보", "기초의원후보", "교육의원후보"):
                continue

            # 대선 회상 투표 reject — "21대 대선 투표 후보" 같은 회상 질문이 기초단체장으로
            # 잘못 분류돼 이재명·김문수·이준석이 시장/군수 후보로 표시되는 케이스 차단.
            if re.search(r"(대선|대통령)\s*(투표|선거|후보)|\d+대\s*대선|회상\s*투표", title):
                continue

            # 정책·현안·방식 질문 reject — 후보 race가 아닌데 office_level로 승격돼 가짜 후보
            # (기존처럼·통합광역·기대전야·전략공천·미래기업)가 새던 것을 차단.
            _ntitle_p = re.sub(r"\s", " ", title)
            # 강한 metric 마커 — 어떤 office든 후보 질문일 수 없음 ("X가 잘하는 점", "공천 방식").
            if re.search(r"잘하는|잘한\s*점|힘써야|할\s*분야|공천\s*방식|방식으로|우선\s*순위"
                         r"|평가\s*이유|인물\s*성향|인물\s*유형|선호\s*인물\s*유형"
                         r"|^사례수$|자유\s*응답|재선\s*가능성|현역\s*[가-힣]+의원", _ntitle_p):
                continue
            # 약한 마커 — parser가 "기타"(비후보)로 분류한 경우만 (전략·시대·체제는 정식 제목에도 출현).
            if election_office == "기타" and re.search(
                    r"선거\s*방식|체제|전략|시대|축소|방안|과제|통합\s*이후|영상|주력해야|해야할", _ntitle_p):
                continue

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
                # 3) 합계 너무 작음(<30%) — 거론율·자유응답 형식. 본선 다자 race는 무응답 포함해도
                # 보통 합 40% 이상. 30% 미만은 일부 후보만 추출됐거나 metric 응답.
                # 교육감은 거론율 보고서 형식이 흔해 제외 (title에 교육감 키워드).
                if metric_type in ("후보지지", "당선가능성") and s < 30 \
                        and "교육감" not in title:
                    continue
            # 찬반 표 잘못 분류 (e.g., "약속하는 후보 지지") → skip
            if metric_type in ("후보지지", "당선가능성") and re.search(r"찬\s*성|반\s*대|폐\s*지|약속하는|찬반", title):
                continue
            # 단일정당 당내 경선·적합도·지지 (예: "더불어민주당 차기 중구청장 후보 적합도",
            # "충북도지사 국민의힘 후보 지지도") → 같은 당 후보끼리라 일반 후보지지 아님.
            # 판별: title에 정당명이 정확히 1개 + (후보|적합|경선|단일화). 일반 폴은 정당명이
            # 0개("○○시장 후보 지지도")거나 여러 개(후보별 정당 나열)라 유지됨.
            if metric_type in ("후보지지", "당선가능성", "적합도"):
                _np = sum(1 for pn in ("더불어민주당", "국민의힘", "조국혁신당", "개혁신당",
                                       "진보당", "정의당", "기본소득당", "새로운미래", "사회민주당")
                          if pn in title)
                if (re.search(r"적합|경선|단일화", title) and _np >= 1) or \
                   (_np == 1 and "후보" in title):
                    continue
                # title이 일반적이어도 후보들의 정당 분포로 적합도/경선 판정:
                # 메이저 정당(더민주·국힘·조국혁신·진보·개혁신·정의)에 4+ 후보면 본선 아닌
                # 정당 내부 적합도/경선 race (예: 18068 안산 더민주 5명, 18040 여수 더민주 6명,
                # 17967 군산 더민주 6명). 3명은 본선 다자 가능성 있어 keep.
                # 무소속은 다자 본선에 흔하므로 카운트 제외.
                _MAJOR = {"더불어민주당", "국민의힘", "조국혁신당", "개혁신당", "진보당",
                          "정의당", "민주당"}
                from collections import Counter as _Cnt
                _pc = _Cnt(c.get("party","") for c in cands
                           if c.get("party") and c.get("party") in _MAJOR)
                if any(v >= 4 for v in _pc.values()):
                    continue
            # 가상 양자대결·맞대결 (시나리오 카드) → 헤드라인 아님. 다자대결·적합도·지지는 유지.
            if metric_type in ("후보지지", "당선가능성", "적합도") and \
               re.search(r"가상\s*대결|가상\s*양자|양자\s*대결|맞대결|\bvs\b|\bVS\b", title):
                continue
            # 신설 분구 보정 (9회 지선) — title에 신설구 이름 있으면 sigungu override.
            # NESDC region은 옛 행정구역으로 표기 (중구→영종/제물포, 서구→검단 등).
            NEW_SIGUNGU_KEYWORDS = ["영종구", "제물포구", "검단구"]
            for kw in NEW_SIGUNGU_KEYWORDS:
                if kw in title:
                    sigungu = kw
                    break

            # NEC roster 기반 office/sigungu 재분류 — 한 PDF에 여러 office 표 있을 때
            # (강원도민 여론조사: 도지사·교육감·시장/군수 다 한 PDF). page 큰 title이
            # 모든 표에 일괄 적용되어 region 기반 분류만 되면 광역·교육감 record가 잘못
            # 기초단체장 페이지에 섞임. 후보들의 sg_typecode로 진짜 office 추정.
            cand_names = [c.get("name","") for c in cands if c.get("name")]
            roster_typecodes = []
            roster_sggs = []
            for nm in cand_names:
                hit = _NEC_ROSTER.get(f"{sido}|{nm}") if _NEC_ROSTER else None
                if hit and hit.get("sg_typecode"):
                    roster_typecodes.append(hit["sg_typecode"])
                    if hit.get("sgg"):
                        roster_sggs.append(hit["sgg"])
            # 다수결로 typecode 결정 (후보들이 같은 race 출마 가정)
            roster_override_office = None  # (office_level, office_label) 강제 override
            if roster_typecodes:
                from collections import Counter
                top_tc = Counter(roster_typecodes).most_common(1)[0][0]
                if top_tc == "3":
                    sigungu = ""
                    roster_override_office = ("광역단체장", "도지사")  # 광역시장도 같은 카테고리
                elif top_tc == "11":
                    sigungu = ""
                    roster_override_office = ("교육감", "교육감")
                elif top_tc == "4" and roster_sggs:
                    top_sgg = Counter(roster_sggs).most_common(1)[0][0]
                    if top_sgg and top_sgg != sigungu:
                        sigungu = top_sgg

            # 후보지지·당선가능성·적합도만 office_level 분류, 나머지는 광역/시도 단위 메트릭
            if metric_type in ("후보지지", "당선가능성", "적합도"):
                if roster_override_office:
                    office_level, office_label = roster_override_office
                else:
                    office_level, office_label = classify_office(title, sido, sigungu)
            else:
                # 정당지지·국정평가·투표의향 — sido(+sigungu) 단위, office_level은 메트릭 자체
                office_level = metric_type
                office_label = metric_type
            # 광역단체장·교육감은 도/광역시 전체 race — sigungu가 붙은 건 그 시군구 응답자만의
            # 부분표본(시군구별 등록의 도지사 cross-tab)이라 광역 결과 아님 → skip.
            if office_level in ("광역단체장", "교육감") and sigungu:
                continue
            # 후보지지·적합도·당선가능성은 race — 후보 2명 미만이면 무의미(메트릭 응답 leak·
            # 다자대결 추출실패의 증상). race가 아닌 단독 카드는 drop.
            if metric_type in ("후보지지", "당선가능성", "적합도"):
                n_named = sum(1 for c in cands if c.get("pct") is not None and c.get("name"))
                if n_named < 2:
                    continue

            # 정당지지 race — party 빈 candidate 제거 (column 매핑 잘못된 row).
            # 또 양대정당(민주·국힘) 모두 있어야 의미 있음 — 단독 정당 record drop.
            if metric_type == "정당지지":
                cands = [c for c in cands if c.get("party")]
                parties = {c.get("party") for c in cands}
                if not ({"더불어민주당", "국민의힘"} <= parties):
                    continue
                # 경선 record는 별도 — title에 "경선"·"단일화" 들어가면 정당지지 page에 부적절
                if re.search(r"경선|단일화|당내", title):
                    continue
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
            # 같은 (sido,sigungu,office,party)에 distinct 이름이 다수면 다른 후보들이라
            # 합치면 안 됨. 또 typo가 아니면 (한 글자 차이 또는 prefix/suffix 관계) 합치지 않음.
            if len(counter) >= 3:
                continue  # 한 정당에 후보 3+ 있는 race는 normalize 비활성 (제주 국힘 다자 등)
            if abs(len(name) - len(canonical)) > 1:
                continue
            # 한 글자 차이(edit-dist ≤1) 또는 prefix 관계인 경우만 typo로 간주
            short, long = (name, canonical) if len(name) < len(canonical) else (canonical, name)
            is_prefix = long.startswith(short) or long.endswith(short)
            same_len_one_diff = (len(name) == len(canonical)
                                 and sum(a != b for a, b in zip(name, canonical)) <= 1)
            if not (is_prefix or same_len_one_diff):
                continue
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
    # 직책·기관 라벨이 후보명으로 추출된 것 (교육감 표에서 "조교수/교육국장 출신" 직책 컬럼).
    title_noise = re.compile(r'(조교수|대학원|^소장$|^교장$|^국장$|교육국장|추대후보|^수후보$'
                             r'|연구회|구청$|^교수$|^원장$|사무국장|^위원$|위원장$|^후보$|^대표$)')
    n_candrm = 0
    for p in polls:
        keep = []
        for c in p.get("candidates", []):
            nm = re.sub(r"\s+", "", c.get("name", ""))
            if not nm:
                keep.append(c); continue
            if nm in party_name_set:
                n_candrm += 1; continue
            if metric_in_name.search(nm) or title_noise.search(nm):
                n_candrm += 1; continue
            keep.append(c)
        p["candidates"] = keep
    if n_candrm:
        print(f"  정당명·메트릭 라벨 candidate 제거 {n_candrm}건", file=sys.stderr)

    # "기타" race 폴 office 복구 — 리얼미터·이너텍 등이 챕터헤더 제목("제2장.조사결과")을
    # 달아 classify_office가 office를 못 잡은 본선 race(office_level='기타'라 사이트 탭에
    # 안 뜸)를, 후보→office 매핑으로 광역단체장/기초단체장/교육감에 재분류한다.
    # 매핑원: (1) 정상분류 폴의 (sido,name)→office_level, (2) NEC 후보자검색 office 캐시.
    name_office_clean: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for p in polls:
        if p["office_level"] in ("광역단체장", "기초단체장", "교육감"):
            for c in p["candidates"]:
                if c.get("name"):
                    name_office_clean[(p["sido"], c["name"])][p["office_level"]] += 1
    nec_off = {}
    _op = ROOT / "data" / "raw" / "nec_candidate_office.json"
    if _op.exists():
        try:
            nec_off = json.loads(_op.read_text(encoding="utf-8"))
        except Exception:
            pass

    def _infer_office(p):
        votes = Counter()
        for c in p["candidates"]:
            nm = c.get("name", "")
            if not nm or c.get("pct") is None:
                continue
            if (p["sido"], nm) in name_office_clean:
                votes[name_office_clean[(p["sido"], nm)].most_common(1)[0][0]] += 1
            elif f"{p['sido']}|{nm}" in nec_off:
                votes[nec_off[f"{p['sido']}|{nm}"]] += 1
        if not votes:
            return ""
        top, n = votes.most_common(1)[0]
        others = sum(v for k, v in votes.items() if k != top)
        return top if (len(votes) == 1 or n >= 2 * others) else ""

    n_reclass = 0
    for p in polls:
        if p["office_level"] != "기타" or p["metric_type"] not in ("후보지지", "당선가능성"):
            continue
        if sum(1 for c in p["candidates"] if c.get("name") and c.get("pct") is not None) < 2:
            continue
        off = _infer_office(p)
        if not off:
            continue
        # 광역단체장·교육감인데 시군구가 붙은 건 부분표본(도 전체 race 아님) → drop
        if off in ("광역단체장", "교육감") and p.get("sigungu"):
            p["candidates"] = []
            continue
        p["office_level"] = off
        p["office_label"] = off
        n_reclass += 1
    polls = [p for p in polls if p.get("candidates")]
    if n_reclass:
        print(f"  기타→office 재분류 {n_reclass}건", file=sys.stderr)

    # race 폴 후보명 검증 — 직책/지역/정책 오추출(국무총리·중앙정부·대표도·정부의소 등)을 드롭.
    # 파서가 이름 대신 직책/문항 컬럼을 집은 record. "실제 후보" 판정:
    #   같은 (sido,office)에서 2개 이상 조사기관에 등장(여러 기관이 같은 garbage를 낼 리 없음)
    #   OR NEC 후보자검색 캐시(정당·office)에 있음(단독폴 legit 후보 보호).
    # race 후보 중 실제후보가 2명 미만이면 그 record는 오추출 → drop. 정상 record는 보존.
    REAL_OFFICES = ("광역단체장", "기초단체장", "교육감")
    agencies_by_name: dict[tuple[str, str], dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for p in polls:
        if p["office_level"] in REAL_OFFICES:
            for c in p["candidates"]:
                if c.get("name"):
                    agencies_by_name[(p["sido"], p["office_level"])][c["name"]].add(p.get("agency", ""))
    nec_names_by_sido: dict[str, set] = defaultdict(set)
    for src_path in (ROOT / "data/raw/nec_candidate_party.json", _op):
        if src_path.exists():
            try:
                for k in json.loads(src_path.read_text(encoding="utf-8")):
                    sido, _, nm = k.partition("|")
                    if nm:
                        nec_names_by_sido[sido].add(nm)
            except Exception:
                pass

    def _known_cand(sido, office, nm):
        return len(agencies_by_name[(sido, office)].get(nm, ())) >= 2 or nm in nec_names_by_sido[sido]

    n_garbage = 0
    kept = []
    for p in polls:
        if p["office_level"] in REAL_OFFICES:
            named = [c["name"] for c in p["candidates"] if c.get("name") and c.get("pct") is not None]
            if len(named) >= 2 and sum(1 for n in named if _known_cand(p["sido"], p["office_level"], n)) < 2:
                # 신규 단독 폴 구제 — 모든 후보가 한국 이름 형식(2-4자 한글)이고
                # 정당이 모두 채워져 있으면 진짜 race로 판정 (NEC roster fetch 전·신규 ntt).
                # 19316 충남 서천군 군수 같은 단독 PDF 첫 등록 케이스 보호.
                all_party = all(c.get("party") for c in p["candidates"]
                                if c.get("name") and c.get("pct") is not None)
                all_korean = all(re.match(r"^[가-힣]{2,4}$", c["name"]) for c in p["candidates"]
                                 if c.get("name") and c.get("pct") is not None)
                if all_party and all_korean:
                    kept.append(p)
                    continue
                n_garbage += 1
                continue
        kept.append(p)
    polls = kept
    if n_garbage:
        print(f"  후보명 오추출 race record drop {n_garbage}건", file=sys.stderr)

    # column-bleed 보정 — 이름 끝에 옆칸 글자 1개가 붙은 OCR/격자 오류(원강수원→원강수,
    # 김경수대→김경수). 끝 글자를 떼면 같은 (sido,office)에서 더 자주 나오는 실명이 될 때만 스냅.
    name_freq: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for p in polls:
        if p["office_level"] in REAL_OFFICES:
            for c in p["candidates"]:
                nm = c.get("name", "")
                if nm and re.fullmatch(r"[가-힣]{2,5}", nm):
                    name_freq[(p["sido"], p["office_level"])][nm] += 1
    n_bleed = 0
    for p in polls:
        if p["office_level"] not in REAL_OFFICES:
            continue
        F = name_freq[(p["sido"], p["office_level"])]
        for c in p["candidates"]:
            nm = c.get("name", "")
            if re.fullmatch(r"[가-힣]{4,5}", nm):
                base = nm[:-1]
                if len(base) >= 2 and F[base] >= 2 and F[base] > F[nm]:
                    c["name"] = base
                    n_bleed += 1
    if n_bleed:
        print(f"  column-bleed 이름 보정 {n_bleed}건", file=sys.stderr)

    # 한 record 안 동일 후보 dedup (pct 큰 쪽 유지). 정당지지는 name이 비어 party가 식별자라
    # name-or-party를 키로 — 안 그러면 모든 정당이 빈 name 하나로 뭉개져 1정당만 남는다.
    n_dup_in = 0
    for p in polls:
        seen = {}
        for i, c in enumerate(p.get("candidates", [])):
            key = c.get("name", "") or c.get("party", "")
            if not key:
                seen[f"_blank{i}"] = c; continue  # 이름·정당 둘 다 없으면 보존(중복판정 안 함)
            cur = seen.get(key)
            if cur is None or (c.get("pct") or 0) > (cur.get("pct") or 0):
                if cur is not None: n_dup_in += 1
                seen[key] = c
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
        # 겹치는 후보의 pct가 "일치"할 때만 클러스터링(=진짜 split/중복 표). 같은 후보가
        # 다른 pct면 다른 시나리오(다자 vs 양자 vs 적합도 — 같은 제목 "제2장.조사결과")라
        # 합치면 max-pct로 합계 100% 초과 garble. disjoint(민주경선 vs 국힘경선)도 별도.
        # 충돌·disjoint는 dedup-by-card가 후보집합 기준으로 하나만 남긴다.
        def _pctmap(p):
            return {(c.get("name", "") or c.get("party", "")): c.get("pct")
                    for c in p["candidates"]
                    if (c.get("name") or c.get("party")) and c.get("pct") is not None}
        clusters = []
        for p in ps:
            pm = _pctmap(p)
            for cl in clusters:
                shared = set(cl["pm"]) & set(pm)
                if shared and all(abs((cl["pm"][k] or 0) - (pm[k] or 0)) <= 1.0 for k in shared):
                    cl["recs"].append(p); cl["pm"].update(pm); break
            else:
                clusters.append({"pm": dict(pm), "recs": [p]})
        for cl in clusters:
            if len(cl["recs"]) == 1:
                merged.append(cl["recs"][0]); continue
            base = cl["recs"][0]
            cands = {}
            for qi, q in enumerate(cl["recs"]):
                for ci, c in enumerate(q.get("candidates", [])):
                    k = c.get("name", "") or c.get("party", "")
                    if not k:
                        cands[f"_blank{qi}_{ci}"] = c; continue
                    cur = cands.get(k)
                    if cur is None or (c.get("pct") or 0) > (cur.get("pct") or 0):
                        cands[k] = c
            base["candidates"] = list(cands.values())
            merged.append(base)
            n_merged += len(cl["recs"]) - 1
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

    # 교육감은 무소속(정치적 중립) — 다른 office의 정당 매핑이 새지 않게 모두 비움
    for p in polls:
        if p.get("office_level") == "교육감":
            for c in p["candidates"]:
                c["party"] = ""

    # 정당 빈 후보에 mapping 적용 (다수결 → NEC 캐시 순)
    n_party_filled = n_party_nec = 0
    for p in polls:
        if p["metric_type"] not in ("후보지지", "당선가능성", "적합도"):
            continue
        if p.get("office_level") == "교육감":
            continue  # 교육감 무소속 — 매핑 skip
        sido = p.get("sido", "")
        for c in p["candidates"]:
            if c.get("party"):
                continue
            name = c.get("name", "")
            if not name:
                continue
            # NEC roster (sg_id=20260603 + 같은 시도 + 같은 시군구 등록) 우선 — 동명이인이라도
            # 같은 race이면 정확. 다수결은 fallback.
            party = ""
            sigungu = p.get("sigungu", "")
            roster_hit = _NEC_ROSTER.get(f"{sido}|{name}") if _NEC_ROSTER else None
            if roster_hit and roster_hit.get("jd") and \
                    (not sigungu or roster_hit.get("sgg") in (sigungu, sido)):
                party = roster_hit["jd"]
            elif cand_party_cache.get(f"{sido}|{name}"):
                party = cand_party_cache[f"{sido}|{name}"]
            else:
                k_sido = (sido, name)
                if k_sido in name_party_by_sido:
                    party = majority(name_party_by_sido[k_sido])
                elif name in name_party_global:
                    party = majority(name_party_global[name])
            if party:
                c["party"] = party
                n_party_filled += 1
    if n_party_nec:
        print(f"  NEC 후보자검색으로 정당 보완: {n_party_nec}건")

    # 단일정당 경선 drop — race인데 후보 전원이 같은 정당이면 본선이 아니라 당내 경선/적합도
    # (예: 국힘 김문수/양향자/함진규, 민주 김동연/추미애/한준호). 챕터헤더 제목으로 적합도
    # 필터를 빠져나온 subsample 문항이 정당 채운 뒤 드러난다. 본선은 정의상 2개 이상 정당.
    # 광역단체장·기초단체장만 — 교육감은 정당공천 금지라 전원 무소속/정당빈이 정상(제외).
    # 교육감 직책 garbage(수후보·대학원 등)는 위 garbage-name 필터가 NEC 교육감 명부로 거른다.
    n_singleparty = 0
    kept = []
    for p in polls:
        if p["office_level"] in ("광역단체장", "기초단체장"):
            named = [c for c in p["candidates"] if c.get("name") and c.get("pct") is not None]
            parties = [c.get("party", "") for c in named]
            distinct_real = set(x for x in parties if x and x != "무소속")
            all_empty = not any(parties)                                     # 직책·공약 garbage
            # 실제 정당 1종뿐(+빈칸 가능)이고 무소속도 없으면 단일정당 경선. 빈칸은 NEC 미등록
            # 경선 주자. 무소속 있으면(호남 민주 vs 무소속 등) 본선일 수 있어 제외.
            single_consensus = len(distinct_real) == 1 and "무소속" not in parties
            if len(named) >= 2 and (all_empty or single_consensus):
                n_singleparty += 1
                continue
        kept.append(p)
    polls = kept
    if n_singleparty:
        print(f"  단일정당 경선·정당빈 race drop {n_singleparty}건", file=sys.stderr)

    # 합계>113% race drop — 지지도는 단일선택이라 후보 합이 ~100 이하(무응답 제외). 113 초과면
    # 여러 시나리오(다자+양자+적합도)가 한 record에 섞였거나 적합도-style(독립 %) 오분류 →
    # 합쳐진 수치라 무의미. (단일정당 경선·merge garble의 잔여 single-record 케이스 정리)
    n_oversum = 0
    kept = []
    for p in polls:
        if p["office_level"] in ("광역단체장", "기초단체장", "교육감"):
            s = sum(c.get("pct") or 0 for c in p["candidates"] if c.get("pct") is not None)
            if s > 113:
                n_oversum += 1
                continue
        kept.append(p)
    polls = kept
    if n_oversum:
        print(f"  합계>113% garble race drop {n_oversum}건", file=sys.stderr)

    # 양자대결·진영 경쟁력 race drop — "오세훈 대 박주민"(양자), "범보수/범진보 경쟁력"(진영
    # 가상)은 본선 아님. grid 재분류가 챕터헤더 탓에 office로 올린 것. 제목에 "대"·경쟁력·
    # 범보수/범진보·가상/양자 마커가 있으면 드롭. (build 메인 루프 가상대결 필터를 못 거친 잔여)
    _VS = re.compile(r"[가-힣]{2,3}\s*대\s*[가-힣]{2,3}|경쟁력|범보수|범진보|가상\s*대결|양자|맞대결"
                     r"|\bvs\b|\bVS\b|만약|다음\s*(두|세|네|다섯|[2-5])\s*명")
    n_vs = 0
    kept = []
    for p in polls:
        if p["office_level"] in ("광역단체장", "기초단체장", "교육감") and _VS.search(p.get("table_title", "")):
            n_vs += 1
            continue
        kept.append(p)
    polls = kept
    if n_vs:
        print(f"  양자대결·경쟁력 race drop {n_vs}건", file=sys.stderr)

    # 메이저 정당 4+ 후보 race drop (후처리) — main loop drop이 dedup merge로 다시 4+ 되는
    # 케이스 보정. title 명백 적합도(17967 "민주당후보선호도") + emit 시점 3명이었으나 같은
    # 표 split records merge로 후보 합쳐져 4+ 된 경우 등. 본선 다자도 한 정당 4+는 드물어
    # 적합도/경선 race로 보는 게 안전.
    _MAJOR_F = {"더불어민주당", "국민의힘", "조국혁신당", "개혁신당", "진보당", "정의당", "민주당"}
    n_party4 = 0
    kept = []
    for p in polls:
        if p["office_level"] in ("광역단체장", "기초단체장"):
            from collections import Counter as _Cnt2
            pc = _Cnt2(c.get("party","") for c in p["candidates"] if c.get("party") in _MAJOR_F)
            if any(v >= 4 for v in pc.values()):
                n_party4 += 1
                continue
        kept.append(p)
    polls = kept
    if n_party4:
        print(f"  메이저정당 4+ 적합도 race drop {n_party4}건", file=sys.stderr)

    # 중복 카드 제거 — 한 등록(ntt)·office·지역 = 한 race. 다자 본선 + 가상 sub-matchup
    # ("만약 다음 세 명" 3자, "제2장.조사결과" 2자)이 같이 추출돼 카드 inflate되던 것을,
    # 후보 최다(=다자 본선)만 남겨 1카드/race로 합친다. tie-break: 표본 큰 것.
    # 경선/적합도는 위 필터들이 미리 제거하므로 "후보 최다"가 본선 다자를 가리킨다.
    seen_card: dict[tuple, int] = {}
    deduped = []
    n_dup = 0
    for p in polls:
        k = (p.get("ntt_id"), p["office_level"], p.get("sido", ""), p.get("sigungu", ""))
        if k not in seen_card:
            seen_card[k] = len(deduped)
            deduped.append(p)
            continue
        n_dup += 1
        idx = seen_card[k]
        prev = deduped[idx]
        score = lambda q: (len(q.get("candidates", [])), q.get("sample_size") or 0)
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
