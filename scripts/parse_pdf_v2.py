"""PDF parse v2 — pdfplumber 격자 기반, 단계 분리.

기존 parse_pdf.py는 word x-좌표 클러스터링이라 column 추정에 brittle.
v2는 PDF의 실제 표 격자(grid)를 그대로 활용. 단계:

  Step A  extract_tables    PDF page → cells matrix (rows × cols, 셀 텍스트)
  Step B  classify_table    표 종류 분류 (후보지지 / 정당지지 / 메트릭 / skip)
  Step C  extract_candids   첫 데이터 row("전체")에서 후보·정당·pct 추출

같은 schema (questions list)로 반환. parse_pdf.py와 호환.
"""

from __future__ import annotations

import re
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

import pdfplumber

# 정당명·헤더 단어·노이즈 검사기는 poll_terms에서 (v1과 공유, v1 의존 없음)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from poll_terms import PARTY_NAMES, HEADER_WORDS, _is_noise_name, detect_office, is_metric_title, PARTY_CANON  # type: ignore

# ---------- Step A: 격자 추출 + 정규화 ----------

# pdfplumber가 wrap된 셀 안에 넣는 구분자 (\n, /) 제거 — 'A\nB'·'A/B' → 'AB'
_WRAP_SEP = re.compile(r"[\n\r/]+")


def _norm_cell(text: Optional[str]) -> str:
    if text is None:
        return ""
    s = str(text)
    # 셀 내부 공백·줄바꿈 제거
    s = _WRAP_SEP.sub("", s)
    s = re.sub(r"\s+", "", s)
    # 방송사 양식 마커 제거: 헤더 셀이 "박형준%"·"*없음모름*%" 형태라
    # %·* 때문에 후보명([가-힣]{2,4}) 매칭이 깨짐. 단위 %는 끝에만 붙으므로 trailing만.
    s = s.replace("*", "")
    if s.endswith("%"):
        s = s[:-1]
    return s


def _normalize_table(raw: list[list[Optional[str]]]) -> list[list[str]]:
    """모든 cell wrap 구분자 제거 + 빈 row drop."""
    out = []
    for row in raw or []:
        nrow = [_norm_cell(c) for c in (row or [])]
        if any(nrow):
            out.append(nrow)
    return out


_PCT_CELL = re.compile(r"^-?\d{1,3}(?:\.\d+)?$|^\(\d+\)$|^$")


def _is_data_row(row: list[str]) -> bool:
    """row의 cells가 대부분 % 값 또는 사례수 패턴이면 data row."""
    nonempty = [c for c in row if c]
    if len(nonempty) < 3:
        return False
    pct_like = sum(1 for c in nonempty if _PCT_CELL.match(c))
    return pct_like >= max(2, int(len(nonempty) * 0.6))


def _merge_multirow_header(table: list[list[str]]) -> tuple[list[str], int]:
    """multi-row header → 한 row로 column-wise concat.
    "전체" 매칭으로 data row 찾기 + fallback으로 "첫 data-row" 휴리스틱.
    "title row" (1개 cell만 채워진 row, 셀 merge로 인한 표 위 title)는 header concat에서 제외.
    반환 (header, data_start_index)."""
    if not table:
        return [], 0
    data_idx = None
    # 1차: "전체" 매칭 (■전체■, ▣전체▣ 등)
    for i, row in enumerate(table):
        if any("전체" in c or "전 체" in c for c in row):
            data_idx = i
            break
    # 2차: % 값 row 휴리스틱 (data로 추정되는 첫 row)
    if data_idx is None:
        for i, row in enumerate(table):
            if _is_data_row(row):
                data_idx = i
                break
    if data_idx is None or data_idx == 0:
        return (table[0] if table else []), 1
    # 0..data_idx-1 row column-wise concat. title row(1개 cell만 채워짐)는 skip.
    n_col = max(len(r) for r in table[:data_idx])
    header = []
    title_skip_rows = set()
    for ri in range(data_idx):
        r = table[ri]
        nonempty = [c for c in r if c]
        if not nonempty:
            continue
        # 패턴 1: 채워진 cell이 1개 + 다른 column이 모두 빈 row (전형적 cell-merge title)
        # 패턴 2: 가장 긴 cell이 10자 초과 + 채워진 cell 비율 < 1/3 (위쪽 title row, 다른 cell도 일부 채워질 수 있음)
        n_col = len(r)
        max_len = max(len(c) for c in nonempty)
        if len(nonempty) == 1 and n_col >= 3:
            title_skip_rows.add(ri)
        elif max_len > 10 and len(nonempty) <= max(2, n_col // 3):
            title_skip_rows.add(ri)
    for ci in range(n_col):
        cells = []
        for ri in range(data_idx):
            if ri in title_skip_rows:
                continue
            r = table[ri]
            if ci < len(r) and r[ci]:
                cells.append(r[ci])
        header.append("".join(cells))
    return header, data_idx


# ---------- Step B: 표 분류 ----------

# title에 들어가면 후보 추출 자체 skip
# 주의: "적합도", "선호도"는 NESDC 양식에서 후보지지 표의 별칭 ("○○시장 적합도" = 후보지지).
# 진짜 메트릭만 여기 — "당선가능성", "이념성향", "직무수행평가" 등.
METRIC_TITLE_KW = (
    "당선가능성", "당선가능",
    "선택기준", "선택이유",
    "이념성향", "정치성향", "보수성향", "진보성향", "선호성향",
    "투표의향", "투표할", "투표여부", "투표참여",
    "정책능력", "정책 능력",
    "국정평가", "국정운영",
    "도덕성", "리더십", "인지도",
    "찬성", "반대", "찬반",
    "직무수행평가", "직무수행", "직무평가",
    "현안", "민생", "시급한", "우선순위",  # "가장 시급한 민생 현안" 등 이슈 응답표
    "정책과제", "정책수행", "공약",
)


def classify_table(table: list[list[str]], title: str, page_text: str) -> str:
    """반환: 'candidate' | 'party' | 'metric' | 'skip'"""
    t = re.sub(r"\s+", "", title)
    if any(k in t for k in METRIC_TITLE_KW):
        return "metric"
    if is_metric_title(title):
        return "metric"
    if not table:
        return "skip"
    header, _ = _merge_multirow_header(table)
    header_join = "".join(header)
    has_party = any(p in header_join for p in PARTY_NAMES)
    # header에 후보명 같은 한글 2-4자 (정당·헤더어 제외)가 있으면 후보지지
    has_cand_cell = False
    for h in header:
        if not h:
            continue
        h_strip = h
        for p in PARTY_NAMES:
            h_strip = h_strip.replace(p, "")
        if len(h_strip) <= 6:
            # 셀 전체가 이름
            m = re.fullmatch(r"[가-힣]{2,4}", h_strip)
            cand = m.group(0) if m else ""
        else:
            # 긴 셀 = "이름+전/현+경력/직책" 패턴만 후보로 인정 (예: 박우량전신안군수).
            # 메트릭 응답(지역경제활성화 등)과 구분: 앞 이름 뒤에 전/현·직책 마커 필요.
            m = re.match(r"^([가-힣]{2,4})(?=.*(전|현|시장|군수|구청장|지사|교육감|의원|장관|소장|위원|대표|총장|후보))", h_strip)
            cand = m.group(1) if m else ""
        if cand and cand not in HEADER_WORDS and not _is_noise_name(cand):
            has_cand_cell = True
            break
    if has_cand_cell:
        return "candidate"
    if has_party:
        return "party"
    return "skip"


# ---------- Step C: 후보·pct 추출 ----------

# 사례수·통계·응답 보기 keyword
SKIP_HEADER_KW = (
    "사례수", "가중값", "조사완료", "조사 완료", "사완료", "사례수(명)",
    "단위", "Base", "구분", "분류", "%", "(", ")",
)
# 후보가 아닌 응답 보기 / 메트릭 column
NONCANDIDATE_KW = (
    "없음", "없다", "모름", "모르겠", "거절", "기타", "그외", "그 외", "외인물",
    "계", "합계", "이외", "다른", "지지정당", "지지없", "응답거절",
    "정당지지", "지지도", "정치현안",
    # 메트릭 표 응답 보기
    "보수성향", "진보성향", "선호성향", "성향", "선호도",
    "투표함", "투표하", "투표할",
    "있다", "있음", "아니다", "찬성", "반대",
    "잘하고", "잘못하고", "어느쪽", "어느쪽도",
    # 조사 방법·메트릭 응답
    "유선", "무선", "대이상", "이상", "이하",
    "매우", "다소", "약간", "대단히",
    "단일", "단일화", "잘하는편", "잘못하는", "잘함",
    # PDF별 메트릭/이슈 응답 키워드
    "정부견제", "경제활성", "대구경북", "정당및지", "도덕성과", "도덕성",
    "지역소멸", "부동산", "교육문제", "청년문제", "관광",
    "신공항", "북부권", "민간사업", "여야정치", "정부의재",
    "미래첨단", "복지",
    "대체로잘", "대체로", "종합", "정도이상",
    "에힘을실",  # "힘을실어줘야" 응답 잘림
)


def _is_skip_header(h: str) -> bool:
    if not h:
        return True
    if any(kw in h for kw in SKIP_HEADER_KW):
        return True
    # NONCANDIDATE은 정당명 안 들어간 column에만 적용
    # (table title이 첫 column header에 합쳐진 경우 "지지도" 같은 단어가 후보 column에 끼는 케이스 보정)
    has_party = any(p in h for p in PARTY_NAMES)
    if not has_party and any(kw in h for kw in NONCANDIDATE_KW):
        return True
    return False


def _find_data_row(table: list[list[str]], data_start: int) -> Optional[list[str]]:
    """전체 row 찾기. data_start 이후에서."""
    for row in table[data_start:]:
        joined = "".join(row)
        if "전체" in joined or "전 체" in joined or "▣" in joined or "■" in joined:
            return row
    # fallback: data_start row 자체
    if data_start < len(table):
        return table[data_start]
    return None


def _parse_pct(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d+)?)", text)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    if v < 0 or v > 100:
        return None
    return v


def extract_candidates(table: list[list[str]], kind: str) -> list[dict]:
    if kind not in ("candidate", "party"):
        return []
    header, data_start = _merge_multirow_header(table)
    data_row = _find_data_row(table, data_start)
    if not data_row:
        return []
    cands = []
    for col_i, h in enumerate(header):
        if _is_skip_header(h):
            continue
        if col_i >= len(data_row):
            continue
        pct = _parse_pct(data_row[col_i])
        if pct is None:
            continue
        # 정당 매칭 (긴 이름 우선) — 약칭(국힘)은 정식명(국민의힘)으로 정규화
        party = ""
        for pname in sorted(PARTY_NAMES, key=len, reverse=True):
            if pname in h:
                party = PARTY_CANON.get(pname, pname)
                break
        name = ""
        if kind == "candidate":
            # 후보명은 정당명에 인접 — "정당+이름"(뒤) 또는 "이름+정당+직책"(앞) 둘 다 처리.
            # 정당명 없으면 셀 맨 앞에서. (전경선현전남도의회의원=무소속 / 여인두현정의당목포…)
            idx = -1
            for pname in sorted(PARTY_NAMES, key=len, reverse=True):
                idx = h.find(pname)
                if idx >= 0:
                    plen = len(pname)
                    break
            if idx >= 0:
                segs = [(h[:idx], True), (h[idx + plen:], False)]  # (앞: 정당직전=last, 뒤: first)
            else:
                segs = [(h, False)]  # 정당 없음 → 맨 앞
            for seg, pick_last in segs:
                seg = re.sub(r"(후보는?)", "", seg)
                found = re.findall(r"[가-힣]{2,4}", seg)
                if not found:
                    continue
                cand = found[-1] if pick_last else found[0]
                # 4자 끝글자가 직책·지역 단글자면 잘린 직책 — 3자로 (이개호국[회의원]→이개호)
                if len(cand) == 4 and cand[-1] in "양강충전남북경구군시도국":
                    cand = cand[:-1]
                if len(cand) == 4 and cand[-1] in "현전":
                    cand = cand[:-1]
                if not _is_noise_name(cand) and cand not in HEADER_WORDS:
                    name = cand
                    break
        # candidate kind인데 name 추출 실패면 skip (정당만 매칭된 column)
        if kind == "candidate" and not name:
            continue
        cands.append({"name": name, "party": party, "pct": pct})
    return cands


# ---------- 표 title 찾기 ----------

# 다양한 marker: [표 N], 【 표 N 】, < 표 N >, ( 표 N ), 표N., Q1., 1.
_TABLE_HDR = re.compile(
    r"(?:[\[【<(［]\s*표\s*(\d+)[-\s]?[\]】>)］]?|^\s*표\s*(\d+)[.\-]|^\s*Q\s*(\d+)\.\s*|^\s*(\d+)\.\s+)"
    r"\s*([^\n\[【<(［]+?)(?=\n|$|【|\[)",
    re.MULTILINE,
)
# table cell 안에서 title이 들어있는 케이스도 (갤럽: row[0] = "표3.강원특별자치도지사직무수행평가")
_CELL_TITLE = re.compile(r"^\s*(?:표\s*(\d+)\.|[\[【]\s*표\s*(\d+)\s*[\]】])\s*(.+)")


def _find_table_title(page_text: str, table_idx: int, first_cell: str = "") -> tuple[str, str]:
    """page text + 표 첫 cell에서 N번째 표 title 찾기."""
    # 1차: 표 첫 cell에 title 들어있는지 (갤럽 양식)
    if first_cell:
        m = _CELL_TITLE.match(first_cell)
        if m:
            no = m.group(1) or m.group(2) or ""
            return m.group(3).strip(), no
    # 2차: page text에서 N번째 marker
    matches = list(_TABLE_HDR.finditer(page_text))
    if table_idx < len(matches):
        m = matches[table_idx]
        no = m.group(1) or m.group(2) or m.group(3) or m.group(4) or ""
        return m.group(5).strip(), no
    # 3차: page text 첫 줄 (대제목 line)
    first_line = page_text.split('\n', 1)[0].strip()
    return first_line, ""


# ---------- Step A: PDF → 격자 캐시 ----------
# 격자 추출은 PDF 열기·extract_tables 호출이 비싸므로 별도 캐시. Step B/C 룰 변경 시
# 재실행 안 해도 되도록.

# 기본 격자검출(lines)이 실패하는 양식(여론조사꽃·한국리서치 등 세로 교차표)용 2차 설정.
# 열 경계를 글자 위치로 잡아 "전체" 행의 % 값을 분리한다. 실패 표에만 적용(자가치유).
_TUNED_SETTINGS = {
    "vertical_strategy": "text", "horizontal_strategy": "lines",
    "snap_tolerance": 5, "text_tolerance": 2,
}


def _cells_of(raw) -> list[list[str]]:
    return [[(c if c is not None else "") for c in (row or [])] for row in (raw or [])]


def _unparsed_ratio(cells: list[list[str]]) -> float:
    """헤더 제외 상위 데이터행의 빈 셀 비율. 격자검출 실패(병합·공백) 시그니처."""
    if len(cells) < 2:
        return 0.0
    ncol = max((len(r) for r in cells), default=0)
    if ncol < 4:
        return 0.0
    body = cells[1:6]
    total = sum(len(r) for r in body) or 1
    empty = sum(1 for r in body for c in r if not str(c).strip())
    return empty / total


def extract_grids_from_pdf(pdf_path: Path) -> dict:
    """PDF → 모든 page의 표 격자 + page_text. Step B/C 입력으로 사용.

    1차는 기본(lines) 전략 — 격자선 있는 표(갤럽 등 OK 다수)에 잘 맞는다.
    그 결과가 "헤더는 있는데 데이터가 빈/병합" 시그니처면(여론조사꽃·한국리서치 등 세로 교차표)
    그 page만 _TUNED_SETTINGS(text 세로)로 한 번 더 추출해 append — "전체" 행 % 값을 분리.
    parse_from_grids가 signature로 중복 제거하므로 둘 다 둬도 안전. (tuned는 0.4s로 저렴)
    """
    pages_out = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for pi, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                try:
                    raw_tables = page.extract_tables() or []
                except Exception:
                    raw_tables = []
                tables = []
                need_tuned = not raw_tables
                for ti, raw in enumerate(raw_tables):
                    cells = _cells_of(raw)
                    tables.append({"table_index": ti, "cells": cells})
                    if _unparsed_ratio(cells) > 0.5:
                        need_tuned = True
                if need_tuned:
                    try:
                        tuned = page.extract_tables(_TUNED_SETTINGS) or []
                    except Exception:
                        tuned = []
                    for raw in tuned:
                        tables.append({"table_index": len(tables),
                                       "cells": _cells_of(raw), "strategy": "tuned"})
                pages_out.append({
                    "page_index": pi,
                    "page_text": page_text,
                    "tables": tables,
                })
    except Exception as e:
        print(f"  grid fail {pdf_path.name}: {e}", file=sys.stderr)
    return {"source_pdf": pdf_path.name, "pages": pages_out}


# ---------- Step B+C: 격자 → questions ----------

def parse_from_grids(grids: dict) -> dict:
    """캐시된 격자에서 questions 추출. PDF 안 열어도 됨."""
    questions = []
    seen_signatures = set()
    source_pdf = grids.get("source_pdf", "")
    for page in grids.get("pages", []):
        page_text = page.get("page_text", "")
        raw_tables = page.get("tables", [])
        for tinfo in raw_tables:
            ti = tinfo.get("table_index", 0)
            raw = tinfo.get("cells", [])
            table = _normalize_table(raw)
            if not table:
                continue
            first_cell = table[0][0] if (table and table[0]) else ""
            title, table_no = _find_table_title(page_text, ti, first_cell)
            kind = classify_table(table, title, page_text)
            if kind in ("metric", "skip"):
                continue
            cands = extract_candidates(table, kind)
            if not cands:
                continue
            office = detect_office(title, page_text) if title else detect_office("", page_text)
            if kind == "candidate":
                # title이 메트릭(국정평가·투표의향)으로 명시되면 그게 진짜 — 응답보기(잘함/잘못함 등)를
                # 후보로 오인한 것이므로 drop. detect_office는 title 기반이라 신뢰.
                if office in ("국정평가", "투표의향"):
                    continue
                # 정당-detect 오탐(후보표인데 정당명만 보고 정당지지로 분류)은 후보지지로 보정.
                if office == "정당지지":
                    office = "후보지지"
            if kind == "party":
                office = "정당지지"
            # 페이지 분할 표 병합 — "X 후보 지지도_계속"은 X의 후보 컬럼이 다음 page로 넘친 것.
            # 직전 질문(같은 title 본체·같은 office)에 후보를 합치고 새 question은 안 만든다.
            base_title = re.sub(r"[_\s]*\(?\s*계\s*속\s*\)?\s*$", "", title)
            if questions and base_title and base_title != title and \
               re.sub(r"[_\s]*\(?\s*계\s*속\s*\)?\s*$", "", questions[-1]["title"]) == base_title and \
               questions[-1]["election_office"] == office:
                exist = {c["name"] for c in questions[-1]["candidates"] if c.get("name")}
                for c in cands:
                    if c.get("name") and c["name"] not in exist:
                        questions[-1]["candidates"].append(c)
                        exist.add(c["name"])
                continue
            sig = (office, tuple(sorted((c.get("name",""), c.get("party",""), c.get("pct")) for c in cands)))
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)
            questions.append({
                "table_no": table_no,
                "title": title,
                "election_office": office,
                "candidates": cands,
            })
    return {"source_pdf": source_pdf, "questions": questions}


# ---------- Combined entry (legacy compatibility) ----------

def parse_pdf_v2(pdf_path: Path) -> dict:
    """PDF에서 직접 (격자 캐시 없을 때). 캐시 있으면 parse_from_grids 사용."""
    grids = extract_grids_from_pdf(pdf_path)
    return parse_from_grids(grids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()
    for inp in args.inputs:
        for path in sorted(Path(".").glob(inp) if "*" in inp else [Path(inp)]):
            result = parse_pdf_v2(path)
            qs_with_cands = sum(1 for q in result["questions"] if q["candidates"])
            print(f"OK   {path.name[:80]} ... {len(result['questions'])} 문항, {qs_with_cands} cands", file=sys.stderr)
            if args.print:
                print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
