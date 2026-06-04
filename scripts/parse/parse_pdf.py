"""NESDC 결과 PDF 파서.

각 PDF에서 표(다자대결·정당지지·교육감 등)를 추출 → JSON.

설계:
- 결과표 PDF 양식은 기관별로 다르지만 텍스트 추출(extract_text)이 표 그리드 추출(extract_tables)보다 robust.
- 핵심 패턴:
  - "[표 N] OOO시장 지지도" / "[표 N] OOO교육감" / "[표 N] 정당지지"
  - 헤더 라인에 후보명·정당명
  - "▣ 전체 ▣ (800) (800) 40 39 1 9 11 100" 같이 숫자 grid

출력 (per PDF):
{
  "source_pdf": <상대경로>,
  "ntt_id": <ID>,
  "questions": [
    {
      "table_no": "3",
      "title": "대구시장 지지도",
      "question_text": "...",
      "election_office": "시장|도지사|교육감|대통령평가|정당지지|투표의향|기타",
      "candidates": [{"name":"김부겸","party":"더불어민주당","pct":40}, ...],
      "crosstabs": {"전체": {...}, "성별": {...}, ...}
    }
  ]
}

원본 traceability: source_url + ntt_id는 메타 CSV에서 join.
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

import pdfplumber

# 선거구·정당·후보 분류 어휘 → poll_terms.py (v1·v2 공통). 모듈 import 시에도 찾도록 path 보강.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poll_terms import (  # noqa: F401,E402
    OFFICE_PATTERNS, PARTY_NAMES, GROUP_NAMES, detect_office,
    HEADER_WORDS, METRIC_TITLE_KEYWORDS, is_metric_title, _is_noise_name,
)



def find_candidates_line(lines: list[str]) -> tuple[list[dict], int] | None:
    """헤더 영역에서 정당·후보 페어를 찾는다.

    한국 여론조사 결과표는 보통:
        ... 더불어민주당 국민의힘 개혁신당 ...
        ... 김부겸     추경호  이수찬 ...
    형태로 정당 라인과 후보 라인이 2-3줄 차지. 가운데 헤더(가중값, 사례수 등)가
    끼는 경우가 많아서 정당 라인 +1~+5 슬라이딩 윈도우로 한글 이름 라인을 찾는다.
    """
    party_line_idx = None
    parties: list[str] = []
    # 정당 헤더가 1-3줄에 걸쳐 split될 수 있어서, 인접 3줄을 합쳐 검사
    for i, ln in enumerate(lines):
        window = " ".join(lines[i : i + 3])
        # 데이터 라인 시작 전까지만
        if re.search(r"▣\s*전체|^\s*전체\s+\(", window):
            break
        hits = [p for p in PARTY_NAMES if p in window]
        uniq: list[str] = []
        for h in sorted(hits, key=len, reverse=True):
            # "민주당" vs "더불어민주당" 같은 substring dedup
            if not any(h in u or u in h for u in uniq):
                uniq.append(h)
        if len(uniq) >= 2:
            party_line_idx = i
            parties = uniq
            break
    if party_line_idx is None:
        return None

    # 후보 라인 후보군: 정당 라인부터 3-6줄 윈도우에서 한글 이름 N개 모이는 줄들 합친다.
    # 일부 양식(충남)은 한 줄에 1명, 다음 줄에 또 1명 식으로 쪼개짐.
    candidates: list[str] = []
    accum_names: list[str] = []
    for off in range(1, 8):
        if party_line_idx + off >= len(lines):
            break
        nxt = lines[party_line_idx + off]
        if re.search(r"[▣■]\s*전\s*체\s*[▣■]?|\(\d+\)\s*\(\d+\)", nxt):
            break
        toks = re.findall(r"[가-힣]{2,4}", nxt)
        names = [t for t in toks if t not in HEADER_WORDS and t not in PARTY_NAMES]
        # 정당명이 부분 매칭되는 토큰("민주당" → "더불어민주당" 포함됨)도 제외
        names = [n for n in names if not any(p.endswith(n) or p.startswith(n) for p in PARTY_NAMES)]
        accum_names.extend(names)
        if len(accum_names) >= len(parties):
            candidates = accum_names[: len(parties)]
            break
    if not candidates and accum_names:
        # 후보 수가 정당 수보다 적으면 정당 수를 맞춰 자름
        candidates = accum_names
        parties = parties[: len(candidates)]

    if not candidates:
        return None
    n = min(len(parties), len(candidates))
    pairs = [{"name": candidates[i], "party": parties[i]} for i in range(n)]
    return pairs, party_line_idx


def find_total_pcts(lines: list[str], from_idx: int, n_cols: int) -> list[float] | None:
    """`▣ 전체 ▣ (800) (800) 40 39 1 9 11 100` 같은 라인에서 숫자 추출."""
    for ln in lines[from_idx:]:
        if re.search(r"전\s*체|▣\s*전체", ln):
            nums = re.findall(r"\d+\.?\d*", ln)
            # 사례수 (n)(n) 빼고 뒤쪽 % 들. 마지막 100은 합계.
            if len(nums) >= n_cols + 2:
                # 첫 두 개는 사례수, 마지막은 100, 가운데가 % 들
                pcts = nums[2 : 2 + n_cols]
                try:
                    return [float(x) for x in pcts]
                except ValueError:
                    return None
    return None


def parse_question_block(block_text: str) -> dict | None:
    """한 표 블록 텍스트에서 후보·지지율·메타 추출."""
    lines = [ln.rstrip() for ln in block_text.splitlines() if ln.strip()]
    if not lines:
        return None

    header_m = re.search(r"\[표\s*(\d+)\]\s*(.+)", lines[0])
    table_no = header_m.group(1) if header_m else ""
    raw_title = header_m.group(2).strip() if header_m else lines[0].strip()
    # 목차의 점선·페이지번호 제거
    title = re.sub(r"[·.\s]{3,}\d+\s*$", "", raw_title).strip()

    # 목차 라인은 본문 데이터가 없으므로 skip
    is_toc = bool(re.search(r"[·.]{5,}", raw_title))
    if is_toc:
        return None

    q_text = ""
    for ln in lines[1:6]:
        m = re.search(r"\[문\s*\d+[^\]]*\]\s*(.+)", ln)
        if m:
            q_text = m.group(1).strip()
            break

    office = detect_office(title, q_text)

    cand_info = find_candidates_line(lines)
    if cand_info:
        pairs, party_line_idx = cand_info
        # 다자대결 후보 표
        # 컬럼 수: 후보 N개 + (없다·모름/무응답 같은 기타 1-3개)
        # 일단 후보 수만 사용
        pcts = find_total_pcts(lines, party_line_idx, len(pairs))
        if pcts:
            for i, p in enumerate(pcts):
                pairs[i]["pct"] = p
    else:
        pairs = []

    return {
        "table_no": table_no,
        "title": title,
        "question_text": q_text,
        "election_office": office,
        "candidates": pairs,
    }


def group_lines(words: list[dict], y_tol: float = 3.0) -> list[list[dict]]:
    """단어를 y(top) 좌표로 라인 그룹핑 (agglomerative).

    인접한 두 단어의 top 차이 ≤ y_tol 이면 같은 라인. round-key 방식은 boundary
    케이스에서 같은 행 단어가 다른 bin에 빠지므로 사용 안 함.
    """
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: w["top"])
    groups: list[list[dict]] = []
    current: list[dict] = [sorted_words[0]]
    for w in sorted_words[1:]:
        if w["top"] - current[-1]["top"] <= y_tol:
            current.append(w)
        else:
            groups.append(current)
            current = [w]
    if current:
        groups.append(current)
    return [sorted(g, key=lambda x: x["x0"]) for g in groups]


def parse_page_coords(page) -> list[dict]:
    """pdfplumber Page wrapper. parse_page_coords_words에 위임."""
    words = page.extract_words(use_text_flow=False)
    page_text = page.extract_text() or ""
    return parse_page_coords_words(words, page_text)


def _split_party_name_words(words: list[dict]) -> list[dict]:
    """fitz가 정당+이름을 한 단어로 추출하는 경우 split.

    예: "이장우개혁신당" → "이장우"(좌측 half) + "개혁신당"(우측 half).
    PDF에 띄어쓰기 없이 붙어있을 때 발생.

    단, t 자체가 정당명이거나 너무 짧으면 split 안 함.
    """
    out: list[dict] = []
    party_set = set(PARTY_NAMES)
    for w in words:
        t = w.get("text", "")
        if len(t) < 5 or not re.fullmatch(r"[가-힣]+", t) or t in party_set:
            out.append(w)
            continue
        # 정당명 suffix 검사 (긴 정당명부터). stem은 한글 2-4자 (사람 이름 길이)
        split_done = False
        for p in sorted(PARTY_NAMES, key=len, reverse=True):
            if not t.endswith(p):
                continue
            stem = t[:-len(p)]
            if not (2 <= len(stem) <= 4):
                continue
            # stem이 다른 정당명에 포함되면 split skip (예: "더불어"는 더불어민주당 일부)
            if any(stem in pp for pp in PARTY_NAMES if pp != p):
                continue
            x0, x1 = w["x0"], w["x1"]
            ratio = len(stem) / len(t)
            mid = x0 + (x1 - x0) * ratio
            out.append({"x0": x0, "x1": mid, "top": w["top"], "bottom": w["bottom"], "text": stem})
            out.append({"x0": mid, "x1": x1, "top": w["top"], "bottom": w["bottom"], "text": p})
            split_done = True
            break
        if split_done:
            continue
        # prefix 검사: "더불어민주당허태정"
        for p in sorted(PARTY_NAMES, key=len, reverse=True):
            if not t.startswith(p):
                continue
            stem = t[len(p):]
            if not (2 <= len(stem) <= 4):
                continue
            if any(stem in pp for pp in PARTY_NAMES if pp != p):
                continue
            x0, x1 = w["x0"], w["x1"]
            ratio = len(p) / len(t)
            mid = x0 + (x1 - x0) * ratio
            out.append({"x0": x0, "x1": mid, "top": w["top"], "bottom": w["bottom"], "text": p})
            out.append({"x0": mid, "x1": x1, "top": w["top"], "bottom": w["bottom"], "text": stem})
            split_done = True
            break
        if not split_done:
            out.append(w)
    return out


def parse_page_coords_words(words: list[dict], page_text: str) -> list[dict]:
    """한 페이지의 words list + 전체 텍스트로 [표 N] 블록들 추출.

    words 형식: {text, x0, x1, top, bottom}. pdfplumber 또는 OCR 출력 호환.
    """
    # PDF에서 정당명+후보명이 한 단어로 추출된 경우 split (fitz가 띄어쓰기 없으면 묶음)
    words = _split_party_name_words(words)
    lines = group_lines(words)
    if not lines:
        return []

    # 페이지 헤더 패턴: 양식별 변형
    #  - [표 N] / 【 표 N 】 (KBS, 채널A)
    #  - 표Ⅰ-N / 표Ⅲ-N : 제목 (리얼미터-TBC 등)
    #  - ●● 제목 (KOPRA 등)
    #  - "표\n제목\n N." (한국갤럽 split 양식)
    #  - 문N) 또는 Q1. (한길리서치, 리얼미터 본문)
    tbl_header = (
        re.search(r"\[표\s*(\d+)\]\s*([^\n\[]+)", page_text)
        or re.search(r"【\s*표\s*(\d+)\s*】\s*([^\n\[【]+)", page_text)
        or re.search(r"표\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]\s*-\s*(\d+)\s*[:.]?\s*([^\n]+)", page_text)
        or re.search(r"^표\s*(\d+)\.\s+([^\n]+)", page_text, re.MULTILINE)  # 한국갤럽
        or re.search(r"●●\s*()(차기[^\n]+|[^\n]*(?:지지도|적합도|선호도|당선)[^\n]*)", page_text)  # KOPRA
        or re.search(r"(?:^|\s)(\d+)\.\s*([가-힣][가-힣0-9 ·]+(?:\([^)]*\))?)", page_text)  # 여론조사꽃 OCR (N. 제목(M))
    )
    # 한국갤럽 split 양식 fallback: "표\n인천광역시 중도보수 교육감 단일후보 적합도\n1."
    # group(1)=번호, group(2)=제목 순서 통일 위해 swap
    if not tbl_header:
        m_alt = re.search(r"표\s*\n([^\n]+(?:지지도|적합도|선호도|당선|평가|투표|지지)[^\n]*)\n\s*(\d+)\.\s*", page_text)
        if m_alt:
            class _M:
                def __init__(self, no, title):
                    self._no = no; self._title = title
                def group(self, i):
                    return self._no if i == 1 else self._title
            tbl_header = _M(m_alt.group(2), m_alt.group(1))
    if tbl_header:
        raw_title = tbl_header.group(2).strip()
        if re.search(r"[·.]{5,}", raw_title):
            return []  # 목차
        table_no = tbl_header.group(1)
        title = re.sub(r"[·.\s]{3,}\d+\s*$", "", raw_title).strip()
        q_m = (
            re.search(r"\[문\s*\d+[^\]]*\]\s*([^\n\[]+)", page_text)
            or re.search(r"Q\s*\d+[.)]\s*([^\n]+)", page_text)
            or re.search(r"문\s*\d+\s*[)\]]\s*([^\n]+)", page_text)
        )
        q_text = q_m.group(1).strip() if q_m else ""
    else:
        # `문N)` 또는 `Q1.` 양식 — title = 문항 첫 줄
        q_m = (
            re.search(r"문\s*(\d+)\s*[)\]]\s*([^\n]+)", page_text)
            or re.search(r"Q\s*(\d+)[.)]\s*([^\n]+)", page_text)
        )
        if not q_m:
            return []
        table_no = q_m.group(1)
        q_text = q_m.group(2).strip()
        title = q_text  # 문항 텍스트가 곧 제목 역할
    # 메트릭 표(후보 선택 기준 등)는 후보 다자대결이 아니라 skip
    if is_metric_title(title) or is_metric_title(q_text):
        return []
    office = detect_office(title, q_text)

    # 데이터 라인 찾기: ▣ / ■ / 전 체 / 전체 + 사례수 패턴 (기관별 마커 다름)
    total_idx = None
    MARKERS = ("▣", "■")
    for i, ln in enumerate(lines):
        toks = [w["text"] for w in ln]
        joined = " ".join(toks)
        if any(m in joined for m in MARKERS) and "전체" in joined.replace("전 체", "전체"):
            total_idx = i
            break
    if total_idx is None:
        for i, ln in enumerate(lines):
            toks = [w["text"] for w in ln]
            if not toks:
                continue
            first = toks[0]
            if first in ("전체", "전 체"):
                # 다음 토큰들에 숫자 (사례수 또는 백분율)가 충분히 있어야 함
                nums = [t for t in toks[1:] if re.match(r"^\(?\d+\.?\d*\)?$", t)]
                if len(nums) >= 4:
                    total_idx = i
                    break
    if total_idx is None:
        return [{"table_no": table_no, "title": title, "question_text": q_text,
                 "election_office": office, "candidates": []}]

    total_line = lines[total_idx]

    # 데이터 라인에서 컬럼 추출: 사례수 (NNN)/(NNN) 토큰 무시, 순수 숫자 토큰만
    # 양식별 case count 위치:
    #  - 앞에 1개: ▣ 전체 ▣ (NNN) (NNN) [data...] [100]
    #  - 앞·끝에 1개씩 (조원씨앤아이): ▣ 전체 ▣ (NNN) [data...] (NNN)
    case_count_idxs = [i for i, w in enumerate(total_line) if re.match(r"\(\d+\)$", w["text"])]
    if len(case_count_idxs) >= 2 and case_count_idxs[-1] >= len(total_line) - 2:
        # 마지막 case count가 행 끝쪽 → 데이터는 첫 case count 다음부터 마지막 case count 전까지
        start = case_count_idxs[0] + 1
        end_idx = case_count_idxs[-1]
    elif case_count_idxs:
        start = case_count_idxs[-1] + 1
        end_idx = len(total_line)
    else:
        start = 0
        end_idx = len(total_line)
    data_cols = []  # (x_center, value_str, value_float)
    for w in total_line[start:end_idx]:
        if re.match(r"^\d+\.?\d*$", w["text"]):
            try:
                v = float(w["text"])
            except ValueError:
                continue
            cx = (w["x0"] + w["x1"]) / 2
            data_cols.append((cx, w["text"], v))
    if not data_cols:
        return [{"table_no": table_no, "title": title, "question_text": q_text,
                 "election_office": office, "candidates": []}]
    # 마지막은 거의 항상 100 (계). 정확히 100이면 제거.
    if abs(data_cols[-1][2] - 100) < 0.5:
        data_cols = data_cols[:-1]

    # 헤더 영역 시작점:
    #  - "[문" / "Q1." / "문)" 라인 다음 (질문문 끝)
    #  - "Base=전체" 라인 다음 (비전코리아 양식)
    # 사례수/조사 가중/단위는 헤더 본문 일부이므로 시작 마커로 쓰지 않음.
    # 기본 fallback: total_idx-8 (적당히 좁게 — 너무 넓으면 표 제목 단어들이 후보로 잡힘).
    header_start = max(0, total_idx - 12)
    for i in range(max(0, total_idx - 20), total_idx):
        joined = " ".join(w["text"] for w in lines[i])
        if joined.startswith("[문") or re.match(r"\[문\s*\d+", joined) or re.match(r"^Q\s*\d+[.)]", joined) or joined.startswith("문)") or re.match(r"^문\s*\)", joined):
            header_start = i + 1
        # 질문문 종료 마커 (?, 주십시오., 무작위순입니다.) → 다음 줄부터 헤더
        if joined.rstrip().endswith(("?", "주십시오.", "주십시오", "순입니다.", "순입니다")):
            header_start = max(header_start, i + 1)
        # "Base=전체" 라인은 같은 라인에 정당명이 같이 있을 수도 (비전코리아).
        # 그 위 1라인까지 포함.
        if "Base" in joined and "전체" in joined:
            header_start = max(header_start, max(0, i - 1))

    # 헤더 단어를 데이터 컬럼(전체 행의 % 위치)에 귀속 (anchored).
    # 독립 클러스터링 대신 데이터 값 cx를 격자 기준점으로 — 좁은 컬럼·split 단어에 robust.
    # 주의: 단일 한글 글자("용","명")는 SKIP에 두지 말 것 — wrap된 후보명 둘째 줄 글자가
    # 함께 사라져 "안수용"→"안수" 같은 잘림이 발생함 (조원씨앤아이 좁은 column 양식).
    SKIP_HEADER = {"가중값", "전체", "전 체", "사례수", "사례수(명)", "(명)", "조사완료",
                   "조사완료사", "조사완료사례수", "조사완료사례수(명)", "적용", "계",
                   "단위", "%", "단위:", "단위:%",
                   "Base=전체", "Base=", "=전체", "Base"}
    # 사례수 cx (괄호값) — 헤더 귀속에서 제외
    case_cxs = [(w["x0"] + w["x1"]) / 2 for w in total_line if re.match(r"\(\d+\)$", w["text"])]
    data_col_cxs = [cx for cx, _, _ in data_cols]
    columns_h: list[list[dict]] = [[] for _ in data_col_cxs]
    for ln in lines[header_start:total_idx]:
        for w in ln:
            t = w["text"]
            if t in SKIP_HEADER or t.startswith("("):
                continue
            cx = (w["x0"] + w["x1"]) / 2
            # 사례수 컬럼에 가까우면 skip
            if any(abs(cx - cc) < 14 for cc in case_cxs):
                continue
            # 가장 가까운 데이터 컬럼에 귀속 (26pt 이내)
            best = min(range(len(data_col_cxs)), key=lambda i: abs(data_col_cxs[i] - cx))
            if abs(data_col_cxs[best] - cx) <= 26:
                columns_h[best].append(w)

    # 각 컬럼의 텍스트 합쳐서 정당·후보 매칭
    party_words: list[tuple[float, str]] = []
    name_words: list[tuple[float, str]] = []
    for col_i, col in enumerate(columns_h):
        if not col:
            continue
        col_cx = data_col_cxs[col_i]  # 데이터 컬럼 cx 고정 (anchored)
        # top 순 정렬해서 join (위에서 아래로) — 공백 없이 합쳐 "더불어민주"+"당"="더불어민주당" 됨
        col.sort(key=lambda w: w["top"])
        joined_no_space = "".join(w["text"] for w in col)
        joined_with_space = " ".join(w["text"] for w in col)

        # 이름 위치 먼저 추정 — 정당 매칭을 "이름 앞"으로 한정하기 위함.
        # (한국리서치 "무소속 한동훈 전 국민의힘 대표"에서 직책의 "국민의힘"을 정당으로 오인 방지)
        # "후보"/"후보는" 라벨이 있으면 그 아래가 이름 (에이스 "조국혁신당 후보 조국").
        label_top = None
        for w in col:
            if w["text"] in ("후보", "후보는"):
                label_top = w["top"]
        # 한국갤럽 양식: "후보" 라벨 없이 [정당][이름][현/전 직책...] 구조.
        # 이름이 정당조각("조국")과 같아도 첫 직책마커("현"/"전") 직전 top-최대 토큰이 곧 이름.
        gallup_name = None
        if label_top is None:
            duty_tops = [w["top"] for w in col if w["text"] in ("현", "전")]
            if duty_tops:
                duty_top = min(duty_tops)
                # <= : 이름과 직책마커가 같은 줄인 경우 포함 ("한동훈 전 국민의힘 대표")
                before = [w for w in col if w["top"] <= duty_top
                          and re.fullmatch(r"[가-힣]{2,4}", w["text"])
                          and w["text"] not in PARTY_NAMES
                          and w["text"] not in HEADER_WORDS
                          and not _is_noise_name(w["text"])
                          and not re.fullmatch(r"[가-힣]{1,2}[구시군]", w["text"])]
                if before:
                    gallup_name = max(before, key=lambda w: w["top"])

        # 정당 매칭 — 긴 이름부터 (substring 우선). 컬럼에 "당" 자가 split되어 빠진
        # 경우 (e.g., "더불어민주" 컬럼 + "당" 컬럼)를 위해 stem 매칭도 허용.
        # 이름 위치를 알면 그 위(이름 앞) 텍스트에서만 정당 찾기 (직책의 정당명 배제).
        name_top_hint = gallup_name["top"] if gallup_name is not None else None
        if name_top_hint is not None:
            pre = [w for w in col if w["top"] <= name_top_hint]
            party_text_ns = "".join(w["text"] for w in pre)
            party_text_sp = " ".join(w["text"] for w in pre)
        else:
            party_text_ns, party_text_sp = joined_no_space, joined_with_space
        matched_party = None
        for pname in sorted(PARTY_NAMES, key=len, reverse=True):
            if pname in party_text_ns or pname in party_text_sp:
                matched_party = pname
                break
            # stem: "더불어민주당" → "더불어민주", "조국혁신당" → "조국혁신"
            if pname.endswith("당") and len(pname) >= 5:
                stem = pname[:-1]
                if stem in party_text_ns:
                    matched_party = pname
                    break
        if matched_party:
            party_words.append((col_cx, matched_party))

        # 단순 [정당][이름] 구조 (직책마커·"후보" 라벨 없음, 18761 평택 등):
        # 정당명을 위에서부터 누적해 완성되는 토큰 바로 아래 첫 2-4자 한글이 이름.
        # 이름이 정당조각("조국")과 같아도 위치로 식별 (일반 경로는 정당조각이라 누락함).
        plain_name = None
        if gallup_name is None and label_top is None and matched_party:
            acc = ""
            party_bottom = None
            stem_p = matched_party[:-1] if (matched_party.endswith("당") and len(matched_party) >= 5) else None
            for w in col:  # top-sorted
                acc += w["text"]
                if matched_party in acc or (stem_p and stem_p in acc):
                    party_bottom = w["top"]
                    break
            if party_bottom is not None:
                belows = [w for w in col if w["top"] > party_bottom
                          and re.fullmatch(r"[가-힣]{2,4}", w["text"])
                          and w["text"] not in PARTY_NAMES
                          and w["text"] not in HEADER_WORDS
                          and not _is_noise_name(w["text"])
                          and not re.fullmatch(r"[가-힣]{1,2}[구시군]", w["text"])]
                if belows:
                    plain_name = min(belows, key=lambda w: w["top"])  # 정당 바로 아래 첫 이름

        # 이름 매칭 — 컬럼당 1명만 (top 최소 = 후보명 라인이 보통 가장 위)
        # 같은 컬럼에 후보명·직책·지역명이 섞일 수 있어 (e.g., "정명희" / "전 북구청장" / "북구")
        scored = []  # (word, after_label)
        for w in col:
            t = w["text"]
            if not re.match(r"^[가-힣]{2,4}$", t):
                continue
            if t in HEADER_WORDS:
                continue
            after_label = label_top is not None and w["top"] > label_top
            # 정당명 조각 skip — 단 "후보" 라벨 뒤 단어는 이름이므로 예외 ("조국" 등)
            if not after_label and any(p in t or t in p for p in PARTY_NAMES):
                continue
            if after_label and t in PARTY_NAMES:  # 라벨 뒤라도 정당명 자체는 이름 아님
                continue
            if t in {"지지도", "출마", "후보는", "후보", "지지율", "투표하시겠습니까",
                     "투표하시", "기호순으로", "불러드립니다", "주십시오",
                     "현", "전", "제17대", "제18대", "제19대", "제20대"}:
                continue
            # 시군구 패턴 (X구/X시/X군 2-3자) — 후보명일 가능성 낮음
            if re.fullmatch(r"[가-힣]{1,2}[구시군]", t):
                continue
            # 언론사·직책·질문문 노이즈 거부
            if _is_noise_name(t):
                continue
            scored.append((w, after_label))
        # 라벨 뒤 후보가 있으면 그것만 사용 (정당조각·지역명 배제)
        if any(a for _, a in scored):
            name_candidates = [w for w, a in scored if a]
        else:
            name_candidates = [w for w, _ in scored]
        if gallup_name is not None:
            best = gallup_name
            best_after_label = True  # 직책 직전 이름 — 완전한 이름, 확장 금지
        elif plain_name is not None:
            best = plain_name
            best_after_label = True  # 정당 아래 첫 이름 — 완전, 확장 금지
        elif name_candidates:
            best = min(name_candidates, key=lambda w: w["top"])
            best_after_label = label_top is not None and best["top"] > label_top
        else:
            best = None
        if best is not None:
            cx = (best["x0"] + best["x1"]) / 2
            best_name = best["text"]
            # best_name이 2자(truncated)면 joined에서 더 긴 한글 sequence 사용 (정당 유무 무관).
            # "김민"→"김민석", "나경"→"나경원". 이미 3자+면 확장 안 함 (KBS "정명희"→"정명희전제" 방지)
            # 단, "후보" 라벨 뒤에서 직접 잡은 이름은 완전한 이름이므로 확장 안 함 ("조국" 보존).
            if len(best_name) < 3 and not best_after_label:
                stem = joined_no_space
                if matched_party:
                    stem = stem.replace(matched_party, "")
                for pname in PARTY_NAMES:
                    stem = stem.replace(pname, "")
                stem = stem.replace("후보는", "").replace("후보", "")  # 라벨 잔재 제거
                # overlap 매칭 (lookahead) — 후보명이 stem 앞쪽 시군구 라벨에 묻혀
                # 첫 non-overlap 매치가 후보명을 비껴 가는 케이스 보정 ("정읍시정도진" → "정도진" 추출).
                # best_name으로 시작하는 cand를 우선 (정도→정도진, 안수→안수용).
                cand_list = []
                for m in re.finditer(r"(?=([가-힣]{3,4}))", stem):
                    cand = m.group(1)
                    if best_name in cand and len(cand) > len(best_name):
                        if cand not in HEADER_WORDS and not re.fullmatch(r"[가-힣]{1,2}[구시군]", cand) and not _is_noise_name(cand):
                            cand_list.append(cand)
                if cand_list:
                    cand_list.sort(key=lambda c: (not c.startswith(best_name), len(c)))
                    best_name = cand_list[0]
            # 이름 끝 직책 suffix 떼기: "김병주전"/"김은혜현"(4자) → "김병주"/"김은혜"(3자).
            # 4자에만 적용 — 3자 이름(주철현·김현 등)의 끝 "현"을 보존.
            if len(best_name) == 4 and best_name[-1] in ("전", "현"):
                best_name = best_name[:-1]
            # 4자 이름이 조사로 끝나면 떼기: "서학원이"(서학원+이) → "서학원"
            if len(best_name) == 4 and best_name[-1] in ("이", "가", "은", "는", "을", "를", "도", "만"):
                best_name = best_name[:-1]
            if not _is_noise_name(best_name):
                name_words.append((cx, best_name))
        elif matched_party:
            # column 내 한글 단어 없지만 정당 매칭 — joined에서 정당명 제거 후 추출
            stem = joined_no_space.replace(matched_party, "")
            for pname in PARTY_NAMES:
                stem = stem.replace(pname, "")
            stem = stem.replace("후보는", "").replace("후보", "")  # 라벨 잔재 제거
            for m in re.finditer(r"[가-힣]{2,4}", stem):
                cand = m.group(0)
                if cand in HEADER_WORDS:
                    continue
                if any(p in cand or cand in p for p in PARTY_NAMES):
                    continue
                if re.fullmatch(r"[가-힣]{1,2}[구시군]", cand):
                    continue
                if _is_noise_name(cand):
                    continue
                name_words.append((col_cx, cand))
                break

    def closest(target_x: float, pool: list[tuple[float, str]], max_dist: float = 30) -> str:
        if not pool:
            return ""
        best = min(pool, key=lambda p: abs(p[0] - target_x))
        return best[1] if abs(best[0] - target_x) <= max_dist else ""

    # office별 분기: 후보지지는 (name,party), 정당지지는 party만, 국정/투표는 카테고리
    if office in ("후보지지", "국회의원후보"):
        candidates = []
        # 정당명 anchor 없는 양식 (조원씨앤아이 등)도 처리
        SKIP_NAME_LABELS = {"그", "외", "그외", "그 외 인물", "그외인물", "인물",
                            "없음", "모름", "무응답", "기타",
                            "여론조사", "보고서", "조사", "통계표", "결과표",
                            "스트레이트뉴스", "지방선거",
                            "차기", "누구를", "누가", "이번", "다음의", "다음",
                            "귀하", "정당", "소속", "가장", "어느", "어디", "이외",
                            "당선", "가능성", "지지도", "적합도", "선호도",
                            "보기는", "순환됩니다", "순환", "출마하는",
                            "선거에", "선거에서", "선거", "후보", "후보들",
                            "순서는", "순서", "무작위", "무작위순", "무작위순입니다",
                            "기호순", "기호순으로",
                            "출마한", "다음후보", "중누가더", "단일후보",
                            "탄소중립", "장관호", "직무", "수행", "평가",
                            "단일화", "협의회",
                            "특별시", "광역시", "특별자치도", "도지사",
                            "시장", "구청장", "군수", "교육감", "지사",
                            # 시도명
                            "서울", "부산", "대구", "인천", "광주", "대전", "울산",
                            "세종", "경기", "강원", "충청", "충북", "충남",
                            "전라", "전북", "전남", "경상", "경북", "경남", "제주",
                            "서울특별시", "부산광역시", "대구광역시", "인천광역시",
                            "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
                            "경기도", "강원도", "충청북도", "충청남도", "전라북도",
                            "전라남도", "경상북도", "경상남도", "제주도",
                            "강원특별자치도", "전북특별자치도", "제주특별자치도"}

        # 비전코리아 양식 fix: cross-tab 행의 row label에서 (정당, 이름) pair 추출
        # 예: "더불어민주당김성태" → split → 인접 word ["더불어민주당", "김성태"]
        # 헤더에서 후보명 누락 시 fallback 매핑.
        party_to_name: dict[str, str] = {}
        for ln in lines[total_idx + 1:total_idx + 60]:  # 데이터 + cross-tab 영역
            for i, w in enumerate(ln):
                t = w["text"]
                if t not in PARTY_NAMES:
                    continue
                if i + 1 >= len(ln):
                    continue
                next_t = ln[i + 1]["text"]
                if not re.fullmatch(r"[가-힣]{2,4}", next_t):
                    continue
                if next_t in SKIP_NAME_LABELS:
                    continue
                if any(pp in next_t or next_t in pp for pp in PARTY_NAMES):
                    continue
                # 첫 매핑만 사용 (가장 위쪽 cross-tab row가 표 주된 cross-tab)
                if t not in party_to_name:
                    party_to_name[t] = next_t

        use_name_only = len(party_words) == 0 and len(name_words) >= 2
        for cx, _, pct in data_cols:
            party = closest(cx, party_words)
            name = closest(cx, name_words)
            if name in SKIP_NAME_LABELS:
                name = ""
            # cross-tab fallback: 헤더에서 못 잡은 이름을 cross-tab pair에서
            if not name and party and party in party_to_name:
                name = party_to_name[party]
            if use_name_only:
                if not name:
                    continue
                candidates.append({"name": name, "party": "", "pct": pct})
            else:
                if not party:
                    continue
                candidates.append({"name": name, "party": party, "pct": pct})
        return [{
            "table_no": table_no, "title": title, "question_text": q_text,
            "election_office": office, "candidates": candidates,
        }]

    if office in ("정당지지", "비례정당"):
        candidates = []
        used_parties = set()
        for cx, _, pct in data_cols:
            party = closest(cx, party_words, max_dist=40)
            if not party or party in used_parties:
                continue
            candidates.append({"name": "", "party": party, "pct": pct})
            used_parties.add(party)
        return [{
            "table_no": table_no, "title": title, "question_text": q_text,
            "election_office": office, "candidates": candidates,
        }]

    if office in ("국정평가", "투표의향"):
        # 컬럼 단위로 합쳐서 T2/B2/모름 net 키워드 매칭
        # T2(1+2) 또는 긍정평가 등 명시적 net 라벨이 있으면 그 cx 사용
        # 없으면 fallback: "잘하고", "잘 함" 등 (단일 컬럼 양식)
        pos_label = "긍정평가" if office == "국정평가" else "투표함"
        neg_label = "부정평가" if office == "국정평가" else "투표안함"
        dk_label = "모름/무응답"

        net_words: list[tuple[float, str]] = []
        has_net = False  # T2/B2 명시 컬럼이 있는지

        for col in columns_h:
            if not col:  # 헤더 단어 안 붙은 % 컬럼 — 0으로 나눔 방지
                continue
            col_cx = sum((cw["x0"] + cw["x1"]) / 2 for cw in col) / len(col)
            joined = "".join(w["text"] for w in col)
            joined_sp = " ".join(w["text"] for w in col)
            # net 컬럼 우선
            if "T2" in joined or "긍정평가" in joined or "긍정 평가" in joined_sp:
                net_words.append((col_cx, pos_label))
                has_net = True
            elif "B2" in joined or "부정평가" in joined or "부정 평가" in joined_sp:
                net_words.append((col_cx, neg_label))
                has_net = True
            elif "모름" in joined or "무응답" in joined:
                net_words.append((col_cx, dk_label))

        # net 컬럼 없으면 fallback — "잘함/잘 함/잘하고", "잘못함/못함" 단일 컬럼 양식
        if not has_net:
            for col in columns_h:
                if not col:
                    continue
                col_cx = sum((cw["x0"] + cw["x1"]) / 2 for cw in col) / len(col)
                joined = "".join(w["text"] for w in col)
                if office == "국정평가":
                    if re.search(r"잘하고|잘\s*함|잘한다|잘하는", joined):
                        net_words.append((col_cx, pos_label))
                    elif re.search(r"잘못|못한다|못하는|못\s*함", joined):
                        net_words.append((col_cx, neg_label))
                else:  # 투표의향
                    if re.search(r"있다|투표함|투표할|할\s*것", joined):
                        net_words.append((col_cx, pos_label))
                    elif re.search(r"없다|안\s*함|안\s*할|않을", joined):
                        net_words.append((col_cx, neg_label))

        entries = []
        used_labels: set[str] = set()
        for cx, _, pct in data_cols:
            label = closest(cx, net_words, max_dist=15)
            if not label or label in used_labels:
                continue
            entries.append({"name": "", "party": label, "pct": pct})
            used_labels.add(label)
        return [{
            "table_no": table_no, "title": title, "question_text": q_text,
            "election_office": office, "candidates": entries,
        }]

    # 기타 office — 데이터 추출 안 함
    return [{
        "table_no": table_no, "title": title, "question_text": q_text,
        "election_office": office, "candidates": [],
    }]


def parse_yeoronjos_page(words: list[dict], page_text: str) -> list[dict]:
    """여론조사꽃 OCR 출력 specific 파서.

    양식 특성:
    - 페이지 헤더: "제2장 결과표 ... 국정 지표-정당지지도N" 등
    - [표 N] 마커 없음
    - 데이터 행: "전체 1009 1009 39 32 ..." (괄호 없는 case count)
    - "전체" → OCR이 "전처"로 잘못 인식하기도

    페이지 1개 = 표 1개 (보통). 전체 행만 추출.
    """
    if not words or not page_text:
        return []

    # 1) 메트릭 종류 — 제목 키워드
    if re.search(r"정당\s*지지도?", page_text):
        office = "정당지지"
    elif re.search(r"국정\s*(운영|평가|지지|수행)", page_text):
        office = "국정평가"
    elif re.search(r"투표\s*(의향|참여|할\s*의향)", page_text):
        office = "투표의향"
    elif re.search(r"(시장|도지사|구청장|군수|교육감).*(지지|선호|후보)", page_text):
        office = "후보지지"
    else:
        return []  # 인식 못 함

    # 2) 제목 추출 — 결과표 다음 한 줄
    title_m = re.search(r"결과표\s*([^\n]+?)(?:\n|$)", page_text)
    if not title_m:
        title_m = re.search(r"국정\s*지표[-\s]*([^\n]+)", page_text)
    title = (title_m.group(1).strip() if title_m else office)[:60]

    # 3) 라인 그룹핑
    lines = group_lines(words, y_tol=4.0)
    if not lines:
        return []

    # 4) 전체/전처 행 찾기 — 첫 토큰이 "전체" 또는 "전처" 인 라인
    total_idx = None
    for i, ln in enumerate(lines):
        if not ln:
            continue
        first = ln[0]["text"]
        if first in ("전체", "전처", "전 체"):
            total_idx = i
            break
    if total_idx is None:
        return []

    total_line = lines[total_idx]
    # 5) 데이터 추출 — 모든 정수/소수 토큰 + cx
    nums = []
    for w in total_line[1:]:  # 첫 토큰 "전체" skip
        t = w["text"]
        if re.match(r"^\d+(\.\d+)?$", t):
            v = float(t)
            cx = (w["x0"] + w["x1"]) / 2
            nums.append((cx, v))
    if len(nums) < 3:
        return []

    # 6) 헤더 컬럼 매칭 — 전체 행 위쪽 라인들 (header) 컬럼별 단어
    case_count_keywords = {"사례수", "사례수(명)", "(명)", "조사", "완료", "가중값", "적용",
                           "Base=전체", "Base-", "=전체"}
    SKIP = {"제2장", "결과표", "단위:", "단위", "%"}
    header_words = []
    case_count_anchor_words = []
    for ln in lines[:total_idx]:
        for w in ln:
            t = w["text"]
            if t in SKIP or t.startswith("("):
                continue
            if t in case_count_keywords:
                case_count_anchor_words.append(w)
                continue
            if re.match(r"^\d", t):
                continue
            header_words.append(w)

    # 사례수/조사완료/가중값 cx (case count 컬럼) — 클러스터링
    case_cxs = []
    for w in sorted(case_count_anchor_words, key=lambda w: (w["x0"] + w["x1"]) / 2):
        cx = (w["x0"] + w["x1"]) / 2
        placed = False
        for i, c in enumerate(case_cxs):
            if abs(c - cx) < 25:
                case_cxs[i] = (c + cx) / 2  # 갱신
                placed = True
                break
        if not placed:
            case_cxs.append(cx)
    # data_nums = nums 중 case_cxs 또는 페이지 끝 cx 500+ (계/사례수)에 가깝지 않은 것
    def is_case_count_cx(cx):
        return any(abs(cx - cc) < 20 for cc in case_cxs)
    data_nums = [n for n in nums if not is_case_count_cx(n[0])]
    # 마지막이 100/1000 (계) 이면 제거
    if data_nums and (abs(data_nums[-1][1] - 100) < 1 or abs(data_nums[-1][1] - 1000) < 5):
        data_nums = data_nums[:-1]
    if not data_nums:
        return []

    # 컬럼 클러스터링 (cx 기준)
    columns_h = []
    for w in sorted(header_words, key=lambda w: ((w["x0"] + w["x1"]) / 2)):
        cx = (w["x0"] + w["x1"]) / 2
        placed = False
        for col in columns_h:
            col_cx = sum((cw["x0"] + cw["x1"]) / 2 for cw in col) / len(col)
            if abs(col_cx - cx) < 20:  # OCR은 좀 넉넉히
                col.append(w)
                placed = True
                break
        if not placed:
            columns_h.append([w])

    # 컬럼별 라벨 — 정당명 또는 카테고리
    col_labels: list[tuple[float, str]] = []
    for col in columns_h:
        col_cx = sum((cw["x0"] + cw["x1"]) / 2 for cw in col) / len(col)
        col.sort(key=lambda w: w["top"])
        joined = "".join(w["text"] for w in col)
        # 정당 매칭 (substring + stem)
        matched = None
        if office in ("정당지지", "비례정당"):
            for pname in sorted(PARTY_NAMES, key=len, reverse=True):
                if pname in joined or (pname.endswith("당") and len(pname) >= 5 and pname[:-1] in joined):
                    matched = pname
                    break
            # OCR 오인 보정: "민주딩"→"민주당", "국민의흐"→"국민의힘", "혁신딩"→"혁신당"
            if not matched:
                normalized = joined.replace("딩", "당").replace("의흐", "의힘").replace("힘ㅁ", "힘")
                for pname in sorted(PARTY_NAMES, key=len, reverse=True):
                    if pname in normalized or (pname.endswith("당") and len(pname) >= 5 and pname[:-1] in normalized):
                        matched = pname
                        break
        elif office == "국정평가":
            if re.search(r"T2|긍정|잘\s*할|잘하", joined):
                matched = "긍정평가"
            elif re.search(r"B2|부정|못\s*할|못하|잘못", joined):
                matched = "부정평가"
            elif "모름" in joined or "무응답" in joined:
                matched = "모름/무응답"
        elif office == "투표의향":
            if re.search(r"있다|투표함|투표할|할\s*의향|할\s*것", joined):
                matched = "투표함"
            elif re.search(r"없다|안\s*할|않을|안\s*함", joined):
                matched = "투표안함"
            elif "모름" in joined or "무응답" in joined:
                matched = "모름/무응답"
        if matched:
            col_labels.append((col_cx, matched))

    if not col_labels:
        return []

    # 7) data_nums와 col_labels 매칭
    # 컬럼 수가 ±1 같으면 순서 매칭이 더 robust (OCR cx 노이즈 회피)
    candidates = []
    used = set()
    col_labels_sorted = sorted(col_labels, key=lambda p: p[0])
    if abs(len(data_nums) - len(col_labels_sorted)) <= 1 and len(col_labels_sorted) >= 2:
        # 순서 매칭
        n = min(len(data_nums), len(col_labels_sorted))
        for i in range(n):
            _, pct = data_nums[i]
            _, label = col_labels_sorted[i]
            if label in used:
                continue
            candidates.append({"name": "", "party": label, "pct": pct})
            used.add(label)
    else:
        # closest cx 매칭 (max_dist 40)
        def closest(target_x, pool, max_dist=40):
            if not pool:
                return ""
            best = min(pool, key=lambda p: abs(p[0] - target_x))
            return best[1] if abs(best[0] - target_x) <= max_dist else ""
        for cx, pct in data_nums:
            label = closest(cx, col_labels)
            if not label or label in used:
                continue
            candidates.append({"name": "", "party": label, "pct": pct})
            used.add(label)

    if not candidates:
        return []

    # 합계 정규화 — 0.1% 단위 (합 800-1100)면 /10
    total = sum(c["pct"] for c in candidates)
    if 700 <= total <= 1200:
        for c in candidates:
            c["pct"] = round(c["pct"] / 10, 1)

    return [{
        "table_no": "",
        "title": title,
        "question_text": "",
        "election_office": office,
        "candidates": candidates,
    }]


def _fitz_words_to_dicts(words) -> list[dict]:
    """fitz tuple → pdfplumber-style dict 변환."""
    return [
        {"x0": w[0], "top": w[1], "x1": w[2], "bottom": w[3], "text": w[4]}
        for w in words
    ]


def parse_pdf(pdf_path: Path, force_ocr: bool = False) -> dict:
    """PDF 전체 파싱 (fitz로 fast path, 깨진 글리프면 OCR fallback)."""
    import fitz  # PyMuPDF — pdfplumber보다 ~100배 빠름

    out = {
        "source_pdf": str(pdf_path.name),
        "ntt_id": pdf_path.name.split("_")[0],
        "questions": [],
        "used_ocr": False,
    }

    # 깨진 글리프 검사 — 첫 ~5페이지 sample
    use_ocr = force_ocr
    if not use_ocr:
        try:
            doc = fitz.open(str(pdf_path))
            sample = ""
            for p in doc[:5]:
                sample += (p.get_text() or "")[:300]
            doc.close()
            from _ocr import is_broken_text
            if is_broken_text(sample):
                use_ocr = True
        except Exception:
            pass

    if use_ocr:
        out["used_ocr"] = True
        from _ocr import ocr_pdf_to_pages
        try:
            pages = ocr_pdf_to_pages(pdf_path, dpi=400)
            # 여론조사꽃 specific 양식인지 — 첫 페이지에 specific 키워드
            is_flower = "여론조사꽃" in pdf_path.name
            for words, full_text in pages:
                if is_flower:
                    blocks = parse_yeoronjos_page(words, full_text)
                else:
                    blocks = parse_page_coords_words(words, full_text)
                for b in blocks:
                    out["questions"].append(b)
        except Exception as e:
            print(f"  OCR 실패 {pdf_path.name}: {e}", file=sys.stderr)
    else:
        try:
            doc = fitz.open(str(pdf_path))
            for p in doc:
                # 페이지별 격리 — 한 표 파싱 실패가 나머지 페이지를 통째로 죽이지 않게.
                try:
                    words = _fitz_words_to_dicts(p.get_text("words"))
                    page_text = p.get_text() or ""
                    blocks = parse_page_coords_words(words, page_text)
                    out["questions"].extend(blocks)
                except Exception as e:
                    print(f"  fitz 페이지 실패 {pdf_path.name} p{p.number + 1}: {e}", file=sys.stderr)
            doc.close()
        except Exception as e:
            print(f"  fitz 실패 {pdf_path.name}: {e}", file=sys.stderr)

    return out


def parse_pdf_hybrid(pdf_path: Path, force_ocr: bool = False) -> dict:
    """격자 캐시 우선 → v2.

    1. data/raw/grids/{stem}.json 있으면 parse_from_grids (PDF 안 열고 즉시)
    2. 캐시 없으면 v2 (PDF 열어 격자 추출 + parse). 결과 캐시 저장
    3. v2가 빈 결과여도 빈 결과로 return — v1 fallback은 OCR PDF에서 hang 위험 있어 보류.
       격자 없는 OCR PDF는 별도 처리 필요 (TODO).
    """
    import sys as _sys
    _scripts_dir = str(Path(__file__).resolve().parents[1])
    if _scripts_dir not in _sys.path:
        _sys.path.insert(0, _scripts_dir)
    grids_path = Path(__file__).resolve().parents[2] / "data/raw/grids" / (pdf_path.stem + ".json")
    try:
        from parse_pdf_v2 import parse_from_grids, extract_grids_from_pdf  # type: ignore
        if grids_path.exists():
            with open(grids_path, encoding="utf-8") as f:
                grids = json.load(f)
        else:
            grids = extract_grids_from_pdf(pdf_path)
            grids_path.parent.mkdir(parents=True, exist_ok=True)
            with open(grids_path, "w", encoding="utf-8") as f:
                json.dump(grids, f, ensure_ascii=False, indent=2)
        # ntt_id 보존 (build_polls가 사용)
        result = parse_from_grids(grids)
        ntt_id = pdf_path.name.split("_", 1)[0]
        result["ntt_id"] = ntt_id
        return result
    except Exception as e:
        print(f"  v2 fail {pdf_path.name}: {e}", file=sys.stderr)
        ntt_id = pdf_path.name.split("_", 1)[0]
        return {"source_pdf": pdf_path.name, "ntt_id": ntt_id, "questions": []}


def _process_one(args_tuple: tuple[str, str]) -> tuple[str, int, int, str]:
    """병렬 worker — (pdf_path, out_dir) → (name, n_questions, n_pct, err)."""
    pdf_path_str, out_dir_str = args_tuple
    pdf_path = Path(pdf_path_str)
    out_dir = Path(out_dir_str)
    try:
        result = parse_pdf_hybrid(pdf_path)
    except Exception as e:
        return (pdf_path.name, 0, 0, str(e))
    qs_with_pct = sum(
        1
        for q in result["questions"]
        if q["candidates"] and any("pct" in c for c in q["candidates"])
    )
    out_path = out_dir / (pdf_path.stem + ".json")
    # 덮어쓰기 가드: grid 추출이 후보 0인데 기존 parsed(OCR/words)에 후보가 있으면 보존.
    # parse_pdf·ocr_hybrid·parse_words가 같은 parsed/ namespace를 써서 clobber 방지.
    if qs_with_pct == 0 and out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            if any(q.get("candidates") for q in prev.get("questions", [])):
                return (pdf_path.name, len(prev["questions"]), 0, "")  # 기존 보존
        except Exception:
            pass
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return (pdf_path.name, len(result["questions"]), qs_with_pct, "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="PDF 파일 또는 글로브")
    ap.add_argument("--out-dir", default="data/raw/parsed", help="JSON 저장 디렉토리")
    ap.add_argument("--print", action="store_true", help="JSON stdout으로 출력")
    ap.add_argument("--skip-existing", action="store_true", help="이미 parsed JSON 있으면 skip")
    ap.add_argument("--jobs", type=int, default=1, help="병렬 워커 수 (>=2면 multiprocessing)")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # 입력 파일 수집
    targets: list[Path] = []
    for inp in args.inputs:
        for path in sorted(Path(".").glob(inp) if "*" in inp else [Path(inp)]):
            out_path = out_dir / (path.stem + ".json")
            if args.skip_existing and out_path.exists():
                continue
            targets.append(path)

    # 단일 PDF + --print 모드 (debugging)
    if args.print and len(targets) <= 3:
        for path in targets:
            try:
                result = parse_pdf_hybrid(path)
            except Exception as e:
                print(f"FAIL {path.name}: {e}", file=sys.stderr)
                continue
            out_path = out_dir / (path.stem + ".json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            qs_with_pct = sum(
                1
                for q in result["questions"]
                if q["candidates"] and any("pct" in c for c in q["candidates"])
            )
            print(f"OK   {path.name[:80]} ... {len(result['questions'])} 문항, {qs_with_pct} pct",
                  file=sys.stderr)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 병렬 또는 직렬 실행
    n_ok = 0
    n_fail = 0
    n_questions = 0
    work = [(str(p), str(out_dir)) for p in targets]

    if args.jobs >= 2:
        from multiprocessing import Pool
        from tqdm import tqdm
        with Pool(args.jobs) as pool:
            for name, n_q, n_pct, err in tqdm(pool.imap_unordered(_process_one, work),
                                              total=len(work), file=sys.stderr):
                if err:
                    print(f"FAIL {name}: {err}", file=sys.stderr)
                    n_fail += 1
                else:
                    n_ok += 1
                    n_questions += n_pct
    else:
        for w in work:
            name, n_q, n_pct, err = _process_one(w)
            if err:
                print(f"FAIL {name}: {err}", file=sys.stderr)
                n_fail += 1
            else:
                n_ok += 1
                n_questions += n_pct
                print(f"OK   {name[:80]} ... {n_q} 문항, {n_pct} pct", file=sys.stderr)

    print(
        f"\n총 {n_ok}개 PDF, 실패 {n_fail}, 추출 {n_questions}개",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
