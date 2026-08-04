"""공약 → 정책 분야 자동 분류 (data/pledges/*.json에 realm_auto 기록).

NEC 응답의 공약분야명(prmsRealmName)은 6,048건 중 45건만 채워져 있다(99.3% 공백).
분류 축이 아예 없으면 '분야별 공약 분포' 같은 걸 만들 수 없어, 제목·본문에서 규칙으로
분야를 추정한다. LLM을 쓰지 않는다 — 이 저장소의 다른 산출물처럼 결정적이고 재실행
가능해야 하고, CI에서 돌 수 있어야 하기 때문.

방법: 분야별 키워드 사전 × 가중 점수.
  · 제목 히트는 본문보다 무겁게 본다(제목이 공약의 주제를 직접 말한다).
  · 본문은 히트 횟수가 아니라 **서로 다른 키워드 종류 수**로 센다. 공약 본문은
    '□ 재원조달방안' 같은 고정 서식이라 '재원'이 97%, '예산'이 39%에 등장한다. 횟수로
    세면 이런 상투어 하나가 분야를 통째로 결정해 버린다(반도체 클러스터 공약이
    '행정·재정'으로 분류되는 식). 종류로 세면 상투어 하나만으로는 문턱을 넘지 못한다.
  · 문턱을 넘는 분야를 **모두** 남긴다(다중 라벨). 지선 공약은 '종합병원 유치 + 산업
    클러스터 + 쇼핑몰'처럼 한 건이 여러 분야에 걸치는 게 흔해서, 하나로 강제하면 나머지
    분야가 통째로 사라진다. 대표 분야(realm_auto)는 최고점, 전체는 realms_auto.
  · 문턱을 넘는 분야가 하나도 없으면 '미분류'. 억지로 붙이는 것보다 비워 두는 편이 낫다.

원본 realm은 건드리지 않는다. NEC가 준 45건은 realm에 그대로 남고, 추정치는
realm_auto(대표)·realms_auto(전체)·realm_score로 따로 들어간다 — 이름으로 '추정치'임을
드러내, 소비하는 쪽이 원본과 섞어 쓰지 않게 한다.

사용:
  python3 scripts/build/classify_pledges.py            # 기록
  python3 scripts/build/classify_pledges.py --report   # 분포·표본만 출력(쓰지 않음)
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLEDGE_DIR = ROOT / "data/pledges"

# 분야 → 키워드. 지방선거 공약에 실제로 쓰이는 표현 위주로, 일반 동사(조성·추진·구축)는
# 어느 분야에나 붙으므로 넣지 않는다.
REALMS: dict[str, tuple[str, ...]] = {
    "주택·도시": (
        "주택", "아파트", "재개발", "재건축", "정비사업", "임대주택", "공공주택", "분양",
        "택지", "도시재생", "역세권", "그린벨트", "개발제한구역", "주거", "빈집", "신도시",
    ),
    "교통": (
        "도로", "철도", "지하철", "전철", "버스", "트램", "광역교통", "환승", "주차장",
        "교통망", "고속도로", "IC", "터널", "교량", "노선", "공항", "항만", "자전거도로",
        "대중교통", "교통체증", "정류장",
    ),
    "경제·일자리": (
        "일자리", "고용", "창업", "기업유치", "산업단지", "산단", "투자유치", "소상공인",
        "전통시장", "상권", "지역경제", "중소기업", "벤처", "스타트업", "일자리창출",
        "경제자유구역", "물류", "수출",
    ),
    "복지": (
        "복지", "어르신", "노인", "장애인", "취약계층", "기초생활", "돌봄", "요양",
        "경로당", "복지관", "수당", "기본소득", "사회적약자", "저소득", "한부모",
    ),
    "보육·아동": (
        "보육", "어린이집", "유치원", "출산", "육아", "아동", "돌봄교실", "산후조리",
        "난임", "저출생", "저출산", "키움", "아이돌봄", "초등돌봄",
    ),
    "교육": (
        "교육", "학교", "학생", "대학", "학력", "교실", "교사", "방과후", "진로",
        "평생학습", "도서관", "장학", "특목고", "혁신학교", "교육청", "학군", "학원",
    ),
    "보건·의료": (
        "의료", "병원", "보건소", "건강", "치매", "정신건강", "응급", "감염병", "백신",
        "공공의료", "의대", "약국", "재활", "검진",
    ),
    "환경·기후": (
        "환경", "기후", "탄소", "미세먼지", "대기질", "재활용", "폐기물", "쓰레기",
        "하수", "정수", "생태", "녹지", "공원", "숲", "하천", "수질", "태양광", "신재생",
        "국가정원", "정원", "악취", "탄소중립",
    ),
    "안전·재난": (
        "안전", "재난", "소방", "방재", "침수", "홍수", "산사태", "지진", "범죄",
        "치안", "CCTV", "교통사고", "노후시설", "붕괴",
    ),
    "문화·체육·관광": (
        "문화", "예술", "축제", "관광", "체육", "스포츠", "박물관", "미술관", "공연",
        "체육관", "수영장", "관광객", "레저", "캠핑", "문화재", "유산",
        "골프장", "파크골프", "생활체육", "관광지",
    ),
    "농림수산": (
        "농업", "농민", "농촌", "축산", "임업", "수산", "어민", "어촌", "농지",
        "농산물", "직불금", "귀농", "스마트팜", "양식",
    ),
    "행정·재정": (
        "행정", "예산", "재정", "조직개편", "공무원", "규제개혁", "청사", "민원",
        "디지털행정", "투명", "부채", "세금", "감사", "자치분권", "주민참여",
    ),
}

TITLE_WEIGHT = 3
CONTENT_CAP = 4          # 분야당 본문 기여 상한 (서로 다른 키워드 종류 수)
MIN_SCORE = 3            # 이 점수를 넘긴 분야만 남긴다
MAX_REALMS = 3           # 한 공약에 붙일 분야 상한 — 너무 벌리면 분포가 흐려진다

_RE = {r: re.compile("|".join(re.escape(k) for k in ks)) for r, ks in REALMS.items()}


def classify(title: str, content: str) -> tuple[list[str], int]:
    """(분야 리스트, 대표 분야 점수). 판단이 서지 않으면 ([], 0).

    동점은 분야명 정렬로 깨서 실행 간 결과가 흔들리지 않게 한다.
    """
    scores: dict[str, int] = {}
    for realm, rx in _RE.items():
        t = len(rx.findall(title or ""))
        c = min(len(set(rx.findall(content or ""))), CONTENT_CAP)
        s = t * TITLE_WEIGHT + c
        if s >= MIN_SCORE:
            scores[realm] = s
    if not scores:
        return [], 0
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:MAX_REALMS]
    return [r for r, _ in ranked], ranked[0][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="쓰지 않고 분포·표본만 출력")
    ap.add_argument("--sample", type=int, default=0, help="표본 N건 제목+분류 출력")
    args = ap.parse_args()

    dist = Counter()
    multi = Counter()
    total = 0
    samples = []
    for fp in sorted(PLEDGE_DIR.glob("*.json")):
        doc = json.loads(fp.read_text(encoding="utf-8"))
        changed = False
        for person in doc.get("people", []):
            for pl in person.get("pledges", []):
                realms, score = classify(pl.get("title", ""), pl.get("content", ""))
                total += 1
                # 분포는 대표 분야 기준 — 다중 라벨을 다 세면 합이 100%를 넘어 읽기 어렵다.
                dist[realms[0] if realms else "(미분류)"] += 1
                if realms:
                    multi[len(realms)] += 1
                if len(samples) < args.sample:
                    samples.append((realms, score, pl.get("title", "")))
                if not args.report:
                    if realms:
                        pl["realm_auto"] = realms[0]
                        pl["realms_auto"] = realms
                        pl["realm_score"] = score
                    else:
                        for k in ("realm_auto", "realms_auto", "realm_score"):
                            pl.pop(k, None)
                    changed = True
        if changed and not args.report:
            fp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    print(f"공약 {total}건", file=sys.stderr)
    for realm, n in dist.most_common():
        print(f"  {realm:<14} {n:>5}  {n / total * 100:>5.1f}%", file=sys.stderr)
    unc = dist["(미분류)"]
    print(f"\n분류율 {(total - unc) / total * 100:.1f}%"
          f" · 분야 1개 {multi[1]} · 2개 {multi[2]} · 3개 {multi[3]}", file=sys.stderr)
    for realms, score, title in samples:
        print(f"  [{'+'.join(realms) or '미분류'}] ({score}) {title}", file=sys.stderr)


if __name__ == "__main__":
    main()
