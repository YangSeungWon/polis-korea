"""리얼미터류 ASCII-아트 cross-tab 결과표 복구 → parsed JSON 재기록.

리얼미터(및 유사) 보도통계표 PDF는 표를 PDF 선(line)이 아닌 텍스트 괘선(+--+ | |)으로
그려, pdfplumber extract_tables가 못 잡아 parse_pdf가 questions:[] (빈 파싱)으로 끝난다.
이 스크립트는 extract_text의 ASCII 표를 컬럼 인덱스 정렬로 직접 파싱해, 빈 파싱인 PDF의
parsed JSON을 덮어쓴다(정상 파싱은 건드리지 않음). build_polls_gen.py / build_polls_pres.py가
그대로 집어간다.

  python3 scripts/parse/recover_realmeter.py --election 21st-general-2020 [--dry-run] [--limit N]

레이아웃: 헤더(정당 2줄 + 후보명) → 사례수 하위헤더(조사완료/가중값) → '전체' 행(헤드라인).
  헤더는 첫 separator 전까지만 수집(하위헤더 오염 차단), '전체' 행 pct를 사례수 칸 수만큼
  offset해 후보열에 위치 정렬. 컬럼 헤더 토큰을 registry 정당명과 prefix 매칭 → 정당/후보 분리.
  2단 레이아웃에서 pdfplumber가 표를 중복 출력 → (title, pct튜플)로 dedup.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = ROOT / "data" / "raw" / "pdf"
PARSED_DIR = ROOT / "data" / "raw" / "parsed"

# 선거 id → 기본 CSV
ELECTION_CSV = {
    "19th-pres-2017": "nesdc_19pres_polls.csv",
    "20th-pres-2022": "nesdc_20pres_polls.csv",
    "21st-pres-2025": "nesdc_21pres_polls.csv",
    "20th-general-2016": "nesdc_20gen_polls.csv",
    "21st-general-2020": "nesdc_21gen_polls.csv",
    "22nd-general-2024": "nesdc_22gen_polls.csv",
    "7th-local-2018": "nesdc_7th_polls.csv",
    "8th-local-2022": "nesdc_8th_polls.csv",
    "9th-local-2026": "nesdc_9th_polls.csv",
}

_REG = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"]
PARTIES = sorted(set(list(_REG) + [e["abbr"] for e in _REG.values() if e.get("abbr")]),
                 key=len, reverse=True)

NUM = re.compile(r"^-?\d+\.?\d*$")
PAREN = re.compile(r"^\(\s*[\d,]+\s*\)$")
NAME = re.compile(r"^[가-힣]{2,4}$")
DROP = {"사례수", "계", "없음", "잘모름", "기타", "기타후보", "기타정당", "없다", "모름", "무응답",
        "조사완료", "가중값", "적용", "비율", "구분", "후보", "전체", "소계", "단체", "없거나"}


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.split("|")]


def is_sep(line: str) -> bool:
    s = line.strip()
    return bool(s) and set(s) <= set("+-| ")


def is_total(line: str) -> bool:
    return bool(re.search(r"[■◈▣]?\s*전\s*체\s*[■◈▣]?", line)) and "|" in line


def split_party_name(combined: str) -> tuple[str, str]:
    for p in PARTIES:
        if combined.startswith(p):
            rest = combined[len(p):]
            return p, ("" if rest in DROP or not NAME.match(rest) else rest)
    return "", (combined if NAME.match(combined) and combined not in DROP else "")


def office_of(title: str) -> str:
    t = title.replace(" ", "")
    if "적합도" in t:
        return "적합도"
    if re.search(r"비례|정당투표", t):
        return "비례정당"
    if re.search(r"정당지지|정당후보지지|지지정당", t):
        return "정당지지"
    if re.search(r"국정|대통령.*평가", t):
        return "국정평가"
    return "후보지지"


def parse_block(hdr_rows: list[list[str]], data_row: list[str], s_idx: int) -> list[dict]:
    ncol = max([len(r) for r in hdr_rows] + [len(data_row)])
    pad = lambda r: r + [""] * (ncol - len(r))
    H = [pad(r) for r in hdr_rows]
    D = pad(data_row)
    # 사례수 칸 수 n(데이터에서 s_idx부터 연속 괄호) → 헤더 후보열 h ↔ 데이터열 h+(n-1).
    n = 0
    while s_idx + n < len(D) and PAREN.match(D[s_idx + n]):
        n += 1
    off = n - 1 if n >= 1 else 0
    out = []
    for h in range(s_idx + 1, ncol):
        di = h + off
        if di >= len(D) or not NUM.match(D[di]):
            continue
        pct = float(D[di])
        if not (0 <= pct <= 100):
            continue
        combined = "".join(H[r][h] for r in range(len(H)) if H[r][h] and H[r][h] != "사례수")
        if not combined or combined in DROP:
            continue
        party, name = split_party_name(combined)
        label = name or party
        if not label or label in DROP:
            continue
        out.append({"name": name, "party": party, "pct": pct})
    return out


def norm_borders(t: str) -> str:
    """표 괘선이 CID 글리프(코리아리서치 등 사설영역 box-drawing)·널바이트인 PDF 정규화 →
    세로선 '|', 가로선 '-', 코너 '+'. ASCII 표 파서가 그대로 동작하게."""
    out = []
    for ch in t:
        o = ord(ch)
        if 0xF0810 <= o <= 0xF081F:           # 사설영역 box-drawing (코리아리서치)
            out.append("|" if o == 0xF081B else ("-" if o == 0xF081A else "+"))
        elif ch == "\x00":                     # 널바이트(입소스 등) → 공백
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def parse_pdf(path: Path) -> list[dict]:
    pdf = pdfplumber.open(path)
    qs, seen = [], set()
    for page in pdf.pages:
        lines = norm_borders(page.extract_text() or "").split("\n")
        i, title = 0, ""
        while i < len(lines):
            l = lines[i]
            # 제목 — 'N.', '문N', '<표 N>' (리얼미터·코리아리서치·입소스 공통)
            if re.match(r"\s*(?:<\s*표|문\s*\d|\d+\.)", l) or ("▣" in l and "|" not in l):
                title = re.sub(r"\s+", " ", re.split(r"[|+]", l)[0]).strip()[:70]
            if "사례수" in l and "|" in l:
                row0 = cells(l)
                s_idx = next((x for x, c in enumerate(row0) if c == "사례수"), None)
                if s_idx is None:
                    i += 1
                    continue
                hdr = [row0]
                j = i + 1
                while j < len(lines) and not is_sep(lines[j]) and not is_total(lines[j]):
                    if "|" in lines[j]:
                        hdr.append(cells(lines[j]))
                    j += 1
                # 전체행 탐색 — 사례수~전체 사이 서브헤더가 기관마다 달라(입소스는 더 많음) window 넉넉히.
                k = j
                while k < len(lines) and k < j + 12 and not is_total(lines[k]):
                    k += 1
                if k < len(lines) and is_total(lines[k]):
                    cand = parse_block(hdr, cells(lines[k]), s_idx)
                    key = (title, tuple(round(c["pct"], 1) for c in cand))
                    if len(cand) >= 2 and key not in seen:
                        seen.add(key)
                        qs.append({"table_no": "", "title": title,
                                   "election_office": office_of(title), "candidates": cand})
                    i = k
            i += 1
    return qs


def _rows_by_y(words, tol=3):
    """pymupdf words → [(y, [(x, text), ...]), ...] (y로 행 그룹, x정렬)."""
    rows = []
    for w in sorted(words, key=lambda w: (round(w[1]), w[0])):
        x0, y0, t = w[0], w[1], w[4]
        if not t.strip():
            continue
        if rows and abs(y0 - rows[-1][0]) <= tol:
            rows[-1][1].append((x0, t))
        else:
            rows.append([y0, [(x0, t)]])
    return rows


def parse_pdf_spaced(path: Path) -> list[dict]:
    """공백정렬 cross-tab (코리아리서치센터·일부 입소스/갤럽) — |괘선 없이 x좌표로 컬럼 정렬.
    pdfplumber는 (cid:N)으로 깨지지만 pymupdf는 한글 정상 → 단어 x좌표로 컬럼 클러스터링.
    '전체' 행의 pct 값 x좌표로 컬럼을 정의하고, 위 헤더 행에서 같은 x의 정당·후보명을 모음."""
    import fitz  # pymupdf
    doc = fitz.open(path)
    qs, seen = [], set()
    for pg in doc:
        rows = _rows_by_y(pg.get_text("words"))
        title = ""
        for ri, (y, cells) in enumerate(rows):
            line = " ".join(t for _, t in cells)
            if re.match(r"^\s*(?:<\s*표|문\s*\d|\d+\.|\[\s*문)", line):
                title = re.sub(r"\s+", " ", line)[:70]
            ln = line.replace(" ", "")
            if not (ln.startswith("전체") or ln.startswith("■전체") or ln.startswith("▣전체")) or ri == 0:
                continue
            vals = [(x, t) for x, t in cells if NUM.match(t) and 0 <= float(t) <= 100]
            if len(vals) < 2:
                continue
            hdr = [c for _, c in rows[max(0, ri - 4):ri]]
            out = []
            for vx, v in vals:
                toks = []
                for hcells in hdr:
                    near = [c for c in hcells if abs(c[0] - vx) < 22]
                    if near:
                        toks.append(min(near, key=lambda c: abs(c[0] - vx))[1])
                combined = "".join(t for t in toks if t not in DROP and not PAREN.match(t))
                if not combined or combined in DROP:
                    continue
                party, name = split_party_name(combined)
                label = name or party
                if not label or label in DROP:
                    continue
                out.append({"name": name, "party": party, "pct": float(v)})
            if len(out) >= 2:
                key = (title, tuple(round(c["pct"], 1) for c in out))
                if key not in seen:
                    seen.add(key)
                    qs.append({"table_no": "", "title": title,
                               "election_office": office_of(title), "candidates": out})
    return qs


def parsed_is_empty(stem: str) -> bool:
    """이 PDF의 기존 parsed JSON이 후보표 0개(빈 파싱)인지 — 정상 파싱은 덮어쓰지 않기 위함."""
    p = PARSED_DIR / (stem + ".json")
    if not p.exists():
        return True
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return True
    return not any(q.get("candidates") and any("pct" in c for c in q["candidates"])
                   for q in d.get("questions", []))


def main():
    ap = argparse.ArgumentParser(description="리얼미터류 ASCII 표 복구 → parsed JSON")
    ap.add_argument("--election", default="21st-general-2020", choices=list(ELECTION_CSV))
    ap.add_argument("--csv", default=None, help="NESDC 메타 CSV(미지정 시 election 기본)")
    ap.add_argument("--agency", default="리얼미터,코리아리서치,입소스",
                    help="대상 기관 키워드(쉼표 구분). 모두 ASCII/CID 괘선 cross-tab.")
    ap.add_argument("--all", action="store_true", help="빈 파싱뿐 아니라 전 대상 재파싱(정상도 덮어씀)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    csv_path = ROOT / (args.csv or f"data/raw/{ELECTION_CSV[args.election]}")
    meta = {r["ntt_id"]: r for r in csv.DictReader(open(csv_path, encoding="utf-8"))}
    if args.agency.strip().lower() == "all":   # 전 기관 — 빈 파싱 PDF 전수 시도(|/CID 괘선 포맷이면 추출).
        targets = list(meta.items())
    else:
        kws = [k.strip() for k in args.agency.split(",") if k.strip()]
        targets = [(nid, m) for nid, m in meta.items()
                   if any(k in m.get("agency", "") for k in kws)]
    if args.limit:
        targets = targets[:args.limit]
    print(f"대상 {args.agency} ({args.election}): {len(targets)} ntt", file=sys.stderr)

    n_patched = n_q = n_skip_ok = n_nofile = 0
    by_eo: dict = {}
    for nid, m in targets:
        pdfs = sorted(PDF_DIR.glob(f"{nid}_*.pdf"))
        if not pdfs:
            n_nofile += 1
            continue
        best_qs, best_pdf = [], None
        for pdf in pdfs:
            if not args.all and not parsed_is_empty(pdf.stem):
                continue  # 이미 정상 파싱 — 보존
            try:
                qs = parse_pdf(pdf)            # pdfplumber | / CID 괘선
                if len(qs) < 2:               # |-파서 빈약 → 공백정렬(pymupdf x좌표) 폴백
                    try:
                        qs2 = parse_pdf_spaced(pdf)
                        if len(qs2) > len(qs):
                            qs = qs2
                    except Exception:
                        pass
            except Exception as e:
                print(f"  ! {nid} {pdf.name[:40]}: {e}", file=sys.stderr)
                continue
            if len(qs) > len(best_qs):
                best_qs, best_pdf = qs, pdf
        if not best_qs:
            if not args.all and all(not parsed_is_empty(p.stem) for p in pdfs):
                n_skip_ok += 1
            continue
        for q in best_qs:
            by_eo[q["election_office"]] = by_eo.get(q["election_office"], 0) + 1
        n_patched += 1
        n_q += len(best_qs)
        if not args.dry_run:
            out = {"source_pdf": best_pdf.name, "ntt_id": nid, "questions": best_qs}
            (PARSED_DIR / (best_pdf.stem + ".json")).write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"복구: {n_patched} ntt, {n_q} questions {by_eo}", file=sys.stderr)
    print(f"  (PDF없음 {n_nofile}, 정상파싱 보존 {n_skip_ok})", file=sys.stderr)
    if args.dry_run:
        print("[dry-run] parsed JSON 미기록", file=sys.stderr)


if __name__ == "__main__":
    main()
