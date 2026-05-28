"""여론조사꽃 자체조사 cross-tab PDF의 광역 카드 정정.

자체조사 PDF가 정당지지·진보적합도·보수적합도·가상대결 A/B/C/D 형태로 구성돼
parse_pdf의 grid 추출이 cross-tab sub-row를 후보 지지율로 잘못 잡는다 (전재수 5.3
같은 한 응답자분류 행 수치). 일반 polls와 달리 본선 단일 race가 없어서 광역 카드를
어떤 question으로 emit할지 ambiguous.

이 도구는:
  1. 결과표 PDF 중 의뢰자=조사기관 자체 패턴 식별 (또는 가상대결 A title 존재)
  2. cid_decode로 한글 복원
  3. "가상대결 A - 후보1 vs 후보2" title 추출 + 전체(N) 첫 두 수치 = 정답
  4. parsed JSON에서 기존 cross-tab questions 후보 비우고
     "{sido}시장|도지사 후보 지지도 (전체)" question 추가 (양자, 정답 수치)

parse_kr_stats main 직후 또는 build_polls 직전 호출.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cid_decode import build_cid_table  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_PDF = ROOT / "data/raw/pdf"
PARSED = ROOT / "data/raw/parsed"

_CID_TABLE = None
_CID_RE = re.compile(r"\(cid:(\d+)\)")


def _repair(s: str) -> str:
    global _CID_TABLE
    if _CID_TABLE is None:
        _CID_TABLE = build_cid_table()
    t = _CID_TABLE
    return _CID_RE.sub(lambda m: chr(t[int(m.group(1))]) if int(m.group(1)) in t else "", s or "")


# 후보→정당 매핑 (자체조사 PDF 흔한 광역 후보들)
_PARTY = {
    # 더민주
    "오중기": "더불어민주당", "전재수": "더불어민주당", "김영춘": "더불어민주당",
    "이재성": "더불어민주당", "박재호": "더불어민주당", "김경수": "더불어민주당",
    "민홍철": "더불어민주당", "김두관": "더불어민주당", "허영": "더불어민주당",
    "박찬대": "더불어민주당", "유정복": "더불어민주당",
    # 국힘
    "이철우": "국민의힘", "박형준": "국민의힘", "김도읍": "국민의힘",
    "조경태": "국민의힘", "서병수": "국민의힘", "박수영": "국민의힘",
    "박완수": "국민의힘", "김태호": "국민의힘", "조해진": "국민의힘",
    "윤한홍": "국민의힘", "김성태": "국민의힘",
    # 조국혁신
    "조국": "조국혁신당",
}

_OFFICE_BY_SIDO = {
    "서울특별시": ("광역단체장", "서울시장"),
    "부산광역시": ("광역단체장", "부산시장"),
    "대구광역시": ("광역단체장", "대구시장"),
    "인천광역시": ("광역단체장", "인천시장"),
    "광주광역시": ("광역단체장", "광주시장"),
    "대전광역시": ("광역단체장", "대전시장"),
    "울산광역시": ("광역단체장", "울산시장"),
    "세종특별자치시": ("광역단체장", "세종시장"),
    "경기도": ("광역단체장", "경기도지사"),
    "강원특별자치도": ("광역단체장", "강원도지사"),
    "충청북도": ("광역단체장", "충북도지사"),
    "충청남도": ("광역단체장", "충남도지사"),
    "전북특별자치도": ("광역단체장", "전북도지사"),
    "전라남도": ("광역단체장", "전남도지사"),
    "경상북도": ("광역단체장", "경북도지사"),
    "경상남도": ("광역단체장", "경남도지사"),
    "제주특별자치도": ("광역단체장", "제주도지사"),
}

# 자체조사 PDF 파일명 시그니처
_FNAME_PAT = re.compile(r"여론조사꽃|결과표.*자체")

# title에서 가상대결 A 후보쌍 추출
_VS_A_RE = re.compile(r"가상대결\s*A?\s*[-–]\s*([가-힣]{2,4})\s*v\s*s\s*([가-힣]{2,4})")
_TOTAL_RE = re.compile(r"^전체\s*\(\d+\)\s+([\d.]+)\s+([\d.]+)")

# garbage 후보명 (parse_pdf cross-tab 오인식)
_GARBAGE = re.compile(
    r"잘름|외른|한물이|국민의|더민|불어주|국진|조혁신|이힘|개혁보|민의힘|조완|사료|값용수"
)


def _extract_vs_a(pdf_path: Path) -> tuple[str, str, float, float] | None:
    """PDF에서 가상대결 A 후보쌍 + 전체 수치 추출. 실패 시 None."""
    try:
        with pdfplumber.open(pdf_path) as P:
            cand1 = cand2 = None
            for page in P.pages:
                t = _repair(page.extract_text() or "")
                tm = _VS_A_RE.search(t)
                if not tm:
                    continue
                for ln in t.split("\n"):
                    rm = _TOTAL_RE.match(ln.strip())
                    if rm:
                        return tm.group(1), tm.group(2), float(rm.group(1)), float(rm.group(2))
                # title 잡았는데 전체행 못 잡으면 다음 페이지로 (다음 가상대결 A 페이지)
    except Exception as e:
        print(f"  {pdf_path.name}: PDF 읽기 실패 {e}", file=sys.stderr)
    return None


def _detect_sido(pdf_path: Path) -> str:
    """파일명/제목으로 sido 추정."""
    name = pdf_path.name
    SIDO_HINT = {
        "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
        "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
        "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
        "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
        "제주": "제주특별자치도",
    }
    for k, v in SIDO_HINT.items():
        if k in name:
            return v
    return ""


def _patch_parsed(json_path: Path, sido: str, cand1: str, cand2: str, pct1: float, pct2: float) -> bool:
    """parsed JSON 갱신. garbage questions 후보 비우고 정답 question 추가/덮어씀."""
    j = json.loads(json_path.read_text(encoding="utf-8"))
    questions = j.get("questions", [])

    # 광역 카드 title (classify_office에 광역단체장으로 잡히게)
    if "도지사" in _OFFICE_BY_SIDO.get(sido, ("", ""))[1]:
        title = f"{_OFFICE_BY_SIDO[sido][1]} 후보 지지도 (전체)"
    elif sido in _OFFICE_BY_SIDO:
        title = f"{_OFFICE_BY_SIDO[sido][1]} 후보 지지도 (전체)"
    else:
        title = "광역단체장 후보 지지도 (전체)"

    # 이미 우리가 추가한 정답 question 있으면 갱신만
    found = False
    for q in questions:
        if q.get("title") == title:
            q["candidates"] = [
                {"name": cand1, "party": _PARTY.get(cand1, ""), "pct": pct1},
                {"name": cand2, "party": _PARTY.get(cand2, ""), "pct": pct2},
            ]
            q["election_office"] = "후보지지"
            found = True
            break

    if not found:
        questions.append({
            "title": title,
            "election_office": "후보지지",
            "candidates": [
                {"name": cand1, "party": _PARTY.get(cand1, ""), "pct": pct1},
                {"name": cand2, "party": _PARTY.get(cand2, ""), "pct": pct2},
            ],
        })

    # garbage cross-tab questions 후보 비움 (정답 title은 제외)
    n_clear = 0
    for q in questions:
        if q.get("title") == title:
            continue
        cs = q.get("candidates", [])
        if not cs:
            continue
        # garbage 이름 1개 이상 또는 후보지지 office인데 5+명 cross-tab
        has_garbage = any(_GARBAGE.search(c.get("name", "")) for c in cs)
        if has_garbage:
            q["candidates"] = []
            n_clear += 1
            continue
        # 후보지지·기타 office이고 (정당지지·오차범위·정책 등 metric 아닌) 다자 cross-tab인 경우
        # — 자체조사 PDF는 적합도·가상대결 외엔 정답 race가 없으므로 다 비움
        if q.get("election_office") in ("후보지지", "기타") and len(cs) >= 2:
            # 단, 단일 후보·단일 정당 같은 metric은 유지
            names = [c.get("name", "") for c in cs]
            if all(n in _PARTY for n in names if n) and len(cs) <= 2:
                # 우리가 추가한 정답 형식 — 보존
                continue
            q["candidates"] = []
            n_clear += 1

    j["questions"] = questions
    json_path.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def main():
    import glob
    n_ok = 0
    n_skip = 0
    for pf in sorted(glob.glob(str(RAW_PDF / "*.pdf"))):
        p = Path(pf)
        if not _FNAME_PAT.search(p.name):
            continue
        # 자체조사 가능성 있음 → PDF에서 가상대결 A 패턴 시도
        result = _extract_vs_a(p)
        if not result:
            n_skip += 1
            continue
        cand1, cand2, pct1, pct2 = result
        sido = _detect_sido(p)
        jpath = PARSED / (p.stem + ".json")
        if not jpath.exists():
            continue
        _patch_parsed(jpath, sido, cand1, cand2, pct1, pct2)
        print(f"  {p.name[:50]} | {sido} | {cand1} {pct1} vs {cand2} {pct2}", file=sys.stderr)
        n_ok += 1
    print(f"cross-tab patch: {n_ok} PDF 적용, {n_skip} skip", file=sys.stderr)


if __name__ == "__main__":
    main()
