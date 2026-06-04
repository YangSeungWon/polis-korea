"""재보궐(VT039) PDF에서 국회의원 후보 지지도 표 직접 추출 + parsed JSON 패치.

parse_kr_stats가 _OFFICE_KW에 '국회의원' 없거나 row 묶기 tolerance가 작아
"전 체" 라벨과 수치 행이 분리되는 PDF (에이스리서치·한국리서치·KSOI 등 통계표)
를 처리 못함. 결과 18771·18818·18638 등 빠짐.

이 도구는 byelection PDF를 직접 PDF 페이지 단위로 보고:
1. "<표X> [지역] 국회의원 (지지도|보궐|적합도)" title 찾음
2. 같은 페이지에서 "전체" 텍스트 + 인접 row 수치 시퀀스 매칭 (row 분리 허용)
3. column header에서 후보명 추출 (PARTY 단편·HEADER 단어 skip)
4. parsed JSON에 election_office='국회의원후보' question 추가

build_byelection이 election_office='국회의원후보' 또는 fallback으로 통과시킴.
parse_pdf 재실행해도 우리가 추가한 question은 보존됨 (clobber 가드 + title이
parse_pdf 분류와 다름).
"""
from __future__ import annotations
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poll_terms import HEADER_WORDS, _is_noise_name  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW_PDF = ROOT / "data/raw/pdf"
PARSED = ROOT / "data/raw/parsed"
META_CSV = ROOT / "data/raw/nesdc_byelection.csv"

# 후보→정당 매핑. NEC roster 또는 수동 (재보궐 본선 후보들).
# build_byelection이 정당 비어있으면 후보로 인정 안 함 → 채워야 함.
_PARTY = {
    # 평택을 (2026 보궐)
    "김용남": "더불어민주당", "유의동": "국민의힘", "조국": "조국혁신당",
    "김재연": "진보당", "황교안": "자유와혁신",
    # 부산 북구갑
    "하정우": "더불어민주당", "박민식": "국민의힘", "김성근": "무소속",
    "한동훈": "무소속", "이영풍": "국민의힘",
    # 하남갑
    "이광재": "더불어민주당", "이용": "국민의힘", "김성열": "개혁신당",
    # 인천 연수구갑
    "송영길": "더불어민주당", "박종진": "국민의힘", "정승연": "개혁신당",
    # 제주 서귀포시
    "김성범": "더불어민주당", "고기철": "국민의힘",
    # 대구 달성군
    "박형룡": "더불어민주당", "이진숙": "국민의힘",
    # 충남 공주부여청양
    "김영빈": "더불어민주당", "윤용근": "국민의힘", "이은창": "개혁신당",
    "김혁종": "무소속", "정연상": "무소속",
    # 부산 북구갑 더민주 적합도 (18047)
    "김의겸": "더불어민주당", "문승우": "더불어민주당", "전수미": "더불어민주당",
    "오지성": "더불어민주당",
}

_PCT = re.compile(r"^\d{1,3}(?:\.\d)?$")
_NAME = re.compile(r"^[가-힣]{2,4}$")
_TITLE_RE = re.compile(
    r"(?:<\s*표\s*\d+\s*>|\[\s*표\s*\d+\s*\]|【\s*표\s*\d+\s*】|표\s*\d+\.)\s*"
    r"([가-힣ㆍ·\s]{2,30}?(?:국회의원|보궐|재선거))"
    r".{0,30}?(?:지지도|적합도|선호도)"
)

# column header에 등장하는 noise 단편 (지역명·관용어). 후보명으로 잘못 잡힘 방지.
# 이미 HEADER_WORDS·_is_noise_name이 일부 처리하지만 통계표 특유 보강.
_COLHDR_NOISE = {
    "부산", "북구", "갑", "을", "병", "정", "서귀포시", "평택시", "달성군",
    "공주시", "부여군", "청양군", "공주", "부여", "청양", "하남시", "하남",
    "연수구", "안산시", "아산시", "남구", "동구", "서구", "중구", "경기도",
    "차기", "어느", "것이", "어떤", "다음", "다섯", "다섯명", "보다", "인물들",
    "인물", "순서는", "보기", "기호", "기호순", "조사완료", "가중값", "사례수",
    "단위", "응답률", "표본오차", "조사", "가중", "값", "기준", "현재",
    "이상", "이하", "이내", "이외", "본인", "선생",
    "더민주", "더불민주",  # 추가 정당 단편
    "혁신", "민의힘", "민의", "기타",
    "자유와", "자유", "와혁",  # "자유와혁신" 단편
    # 18047·18614·18636·18638·18678 등에서 후보 자리로 잘못 잡힌 column header 토큰
    "보기는", "거론되고", "되고", "되는", "있는", "있다", "출마가", "출마", "무작위",
    "되어", "되었", "다음의", "위에", "아래", "안에", "사람", "사람의", "사람들",
    "주신", "주신다면",
    "생각하는", "생각", "하는", "선생", "선생님께서는", "하시", "하시겠습니까",
}


def _rows(page, ytol: float = 6.0):
    """word를 행(top) 단위 묶기. ytol 크면 분리 row를 인접하게 묶음 (전체+수치)."""
    rows: dict[float, list] = defaultdict(list)
    for w in page.extract_words(x_tolerance=1.5, keep_blank_chars=False):
        rows[round(w["top"] / ytol) * ytol].append(((w["x0"] + w["x1"]) / 2, w["text"]))
    return sorted((t, sorted(v)) for t, v in rows.items())


def _flat(toks):
    return re.sub(r"\s", "", "".join(t for _, t in toks))


def _is_clean_name(tt: str) -> bool:
    return (_NAME.match(tt) is not None and tt not in HEADER_WORDS
            and tt not in _COLHDR_NOISE and not _is_noise_name(tt))


def extract_byelect_table(rows) -> list[dict]:
    """페이지 rows에서 국회의원 후보 지지도 표 한 개를 추출."""
    # title: "<표N> ... 국회의원 ... 지지도" 짧은 행
    title = ""
    title_ri = -1
    for ri, (top, toks) in enumerate(rows):
        line = " ".join(t for _, t in toks)
        if _TITLE_RE.search(line):
            title = line.strip()
            title_ri = ri
            break
    if not title:
        return []

    # 전체 행: row "전체"로 시작하거나 인접 row pair (■ 전 체 ■ + 수치 행) merge.
    # ytol=6으로 묶었지만 그래도 분리되면 title 이후 첫 "전 체"·"전체"·"BASE:전체" 텍스트 행 +
    # 그 위·아래 인접 row의 수치 행을 합쳐서 본다.
    total_pcts = None
    total_ri = -1
    for ri in range(title_ri + 1, len(rows)):
        flat = _flat(rows[ri][1])
        if re.search(r"(BASE:?전체|전체|^■전체|■전체■|▣전체|^전체)", flat):
            # 자체 row 수치
            self_pcts = [(x, float(t)) for x, t in rows[ri][1]
                         if _PCT.match(t) and 0 <= float(t) <= 100]
            if len(self_pcts) >= 2:
                total_pcts = self_pcts
                total_ri = ri
                break
            # 인접 row (위/아래 1-2개) 검사
            for off in (-1, +1, -2, +2):
                ti = ri + off
                if 0 <= ti < len(rows):
                    near = [(x, float(t)) for x, t in rows[ti][1]
                            if _PCT.match(t) and 0 <= float(t) <= 100]
                    if len(near) >= 2:
                        total_pcts = near
                        total_ri = ri
                        break
            if total_pcts:
                break
    if not total_pcts or len(total_pcts) < 2:
        return []

    # column header 토큰: title 이후 ~ total 직전 + total ±1 (xy mismatch 대비)
    header_toks: list[tuple[float, float, str]] = []
    start = title_ri + 1
    end = total_ri
    for ri in range(start, end + 1):
        top = rows[ri][0]
        for x, t in rows[ri][1]:
            tt = re.sub(r"\s", "", t)
            if _is_clean_name(tt):
                header_toks.append((x, top, tt))

    if len({t for _, _, t in header_toks}) < 2:
        return []

    # x별 nearest topmost-clean = 후보명
    cands = []
    used = set()
    for px, pv in total_pcts:
        near = sorted(((top, nm) for x, top, nm in header_toks if abs(px - x) <= 25),
                      key=lambda z: z[0])
        if near and near[0][1] not in used:
            used.add(near[0][1])
            nm = near[0][1]
            cands.append({"name": nm, "party": _PARTY.get(nm, ""), "pct": pv})
    if len(cands) < 2:
        return []
    return [{"title": title, "election_office": "국회의원후보", "candidates": cands}]


def _load_byelect_ntts() -> set[str]:
    if not META_CSV.exists():
        return set()
    return {r["ntt_id"] for r in csv.DictReader(open(META_CSV, encoding="utf-8"))}


def _candidate_has_pct(question: dict) -> bool:
    """candidate에 실제 후보명(빈 string 아님) + pct가 있는지."""
    for c in question.get("candidates", []):
        if c.get("name") and c.get("pct") is not None:
            return True
    return False


def main():
    targets = _load_byelect_ntts()
    n_ok = n_skip = 0
    for ntt in sorted(targets):
        pdfs = sorted(RAW_PDF.glob(f"{ntt}_*.pdf"))
        if not pdfs:
            n_skip += 1
            continue
        jpath = PARSED / (pdfs[0].stem + ".json")
        if not jpath.exists():
            n_skip += 1
            continue
        j = json.loads(jpath.read_text(encoding="utf-8"))
        # 이미 후보지지 question 있고 후보명 채워져있으면 skip
        existing = [q for q in j.get("questions", [])
                    if q.get("election_office") in ("국회의원후보", "후보지지")
                    and _candidate_has_pct(q)]
        if existing:
            n_skip += 1
            continue

        # PDF 페이지 순회하며 첫 번째 byelect 후보 지지도 표 추출
        found = None
        try:
            with pdfplumber.open(pdfs[0]) as P:
                for page in P.pages:
                    extracted = extract_byelect_table(_rows(page))
                    if extracted:
                        found = extracted[0]
                        break
        except Exception as e:
            print(f"  {ntt}: PDF 읽기 실패 {e}", file=sys.stderr)
            n_skip += 1
            continue
        if not found:
            n_skip += 1
            continue

        # parsed JSON에 추가
        j.setdefault("questions", []).append(found)
        jpath.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {ntt}: + {[(c['name'], c['pct']) for c in found['candidates']]}", file=sys.stderr)
        n_ok += 1

    print(f"byelection patch: {n_ok} ntt 추출, {n_skip} skip", file=sys.stderr)


if __name__ == "__main__":
    main()
