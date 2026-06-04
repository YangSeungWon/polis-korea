"""PDF 파싱 품질 하네스 — 코퍼스 전체 funnel 측정.

파서를 PDF 하나씩 두드려 맞추지 말고, 이 지표를 전/후로 비교하며 구조를 고친다.
메타(sub_election)와 교차해 "후보/정당 결과가 나와야 하는" 조사만 분모로 삼고,
각 등록(ntt_id)을 다음으로 분류한다:

  ok            기대 ✓ · 파싱 ✓ · 누출 없음
  leak          파싱은 됐지만 후보지지에 메트릭/정당 응답이 후보로 새어듦
  parse_fail    결과 PDF(표 있음)는 있는데 후보를 0개 추출
  no_result_pdf 결과표/집계표가 없고 설문지·보도자료뿐 (재수집 대상)
  image_no_table 모든 PDF가 표 0개 (이미지/스캔 → OCR 대상)
  not_expected  현안·정책 조사 등 후보 결과가 애초에 없는 게 정상

이 분류기는 파서 내부에 의존하지 않는다(측정은 측정 대상과 독립). 자체 어휘 사용.

사용:
  .venv/bin/python scripts/audit/audit_parse.py                 # 요약 funnel
  .venv/bin/python scripts/audit/audit_parse.py --list leak     # 한 분류의 ntt_id 덤프
  .venv/bin/python scripts/audit/audit_parse.py --json out.json # 기계용 리포트
  .venv/bin/python scripts/audit/audit_parse.py --baseline      # 직전 리포트와 diff
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
META_CSV = ROOT / "data/raw/nesdc_9th_polls.csv"
GRIDS_DIR = ROOT / "data/raw/grids"
PARSED_DIR = ROOT / "data/raw/parsed"
REPORT = ROOT / "data/raw/parse_audit.json"  # --baseline diff 기준

# 후보/정당 결과가 나와야 하는 조사 (메타 sub_election 키워드)
EXPECT_KW = ("단체장선거", "교육감선거", "정당지지도", "의원선거", "후보")

# 결과 표 PDF vs 비결과 PDF (파일명 키워드)
RESULT_KW = ("결과표", "집계표", "결과집계", "통계표", "결과")
NONRESULT_KW = ("설문지", "보도자료", "요약", "질문지")

# 후보지지에 새면 안 되는 응답 — 메트릭/현안/정당 시그니처 (측정용, 보수적으로)
LEAK_KW = (
    "현정부", "정부지", "정부의", "잘함", "잘못함", "잘하", "잘못하",
    "경제및", "경제·", "일자리", "저출생", "교통문제", "부동산", "지역현안",
    "신공항", "관광", "민생", "복지확", "안전한", "교육문제", "청년",
)
PARTY_WORDS = (
    "더불어민주당", "국민의힘", "조국혁신당", "개혁신당", "진보당", "정의당",
    "기본소득당", "여성의당", "새로운미래", "사회민주당", "무소속",
)


def _ntt(path: str) -> str:
    return Path(path).name.split("_", 1)[0]


def _file_kind(fname: str) -> str:
    for kw in NONRESULT_KW:
        if kw in fname:
            return "nonresult"
    for kw in RESULT_KW:
        if kw in fname:
            return "result"
    return "unknown"


def build_maps() -> tuple[dict, dict, dict]:
    """ntt_id → {has_table, has_result_pdf, has_candidates, leak_names}."""
    has_table = defaultdict(bool)
    for g in glob.glob(str(GRIDS_DIR / "*.json")):
        try:
            d = json.loads(Path(g).read_text(encoding="utf-8"))
        except Exception:
            continue
        if sum(len(p.get("tables", [])) for p in d.get("pages", [])) > 0:
            has_table[_ntt(g)] = True

    has_result_pdf = defaultdict(bool)
    for f in glob.glob(str(ROOT / "data/raw/pdf/*.pdf")):
        if _file_kind(Path(f).name) == "result":
            has_result_pdf[_ntt(f)] = True

    parsed = {}  # ntt → (has_cand, leak_names)
    for p in glob.glob(str(PARSED_DIR / "*.json")):
        ntt = _ntt(p)
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        has_cand = False
        leaks = []
        for q in d.get("questions", []):
            if not q.get("candidates"):
                continue
            has_cand = True
            if q.get("election_office") != "후보지지":
                continue
            for c in q["candidates"]:
                nm = c.get("name", "")
                if not nm:
                    continue
                if nm in PARTY_WORDS or any(s in nm for s in LEAK_KW):
                    leaks.append(nm)
        prev = parsed.get(ntt)
        # 같은 ntt 여러 PDF → 후보 있으면 합침
        parsed[ntt] = (has_cand or (prev[0] if prev else False),
                       (leaks + (prev[1] if prev else [])))
    return has_table, has_result_pdf, parsed


def classify() -> tuple[list[dict], Counter]:
    has_table, has_result_pdf, parsed = build_maps()
    rows = list(csv.DictReader(open(META_CSV, encoding="utf-8")))
    out = []
    cat = Counter()
    for r in rows:
        ntt = r["ntt_id"]
        sub = r.get("sub_election", "")
        expected = any(k in sub for k in EXPECT_KW)
        has_cand, leaks = parsed.get(ntt, (False, []))
        if not expected:
            c = "not_expected_got" if has_cand else "not_expected"
        elif has_cand and leaks:
            c = "leak"
        elif has_cand:
            c = "ok"
        elif not has_table.get(ntt):
            c = "image_no_table"
        elif not has_result_pdf.get(ntt):
            c = "no_result_pdf"
        else:
            c = "parse_fail"
        cat[c] += 1
        out.append({"ntt_id": ntt, "cat": c, "sub": sub[:50],
                    "leaks": sorted(set(leaks))[:6]})
    return out, cat


CAT_LABEL = {
    "ok": "✅ 정상 (기대✓·파싱✓·깨끗)",
    "leak": "⚠️  누출 (후보지지에 메트릭/정당)",
    "parse_fail": "❌ 파싱실패 (결과표 있는데 후보0)",
    "no_result_pdf": "📄 결과PDF없음 (설문지뿐 → 재수집)",
    "image_no_table": "🖼  이미지/OCR (표0)",
    "not_expected": "· 현안조사 등 (정상)",
    "not_expected_got": "+ 보너스 (기대X·파싱✓)",
}
CAT_ORDER = ["ok", "leak", "parse_fail", "no_result_pdf", "image_no_table",
             "not_expected", "not_expected_got"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", metavar="CAT", help="해당 분류의 ntt_id·sub 덤프")
    ap.add_argument("--json", metavar="PATH", help="기계용 리포트 저장")
    ap.add_argument("--baseline", action="store_true",
                    help="직전 parse_audit.json과 분류별 diff")
    args = ap.parse_args()

    out, cat = classify()
    total = len(out)
    expected_total = total - cat["not_expected"] - cat["not_expected_got"]

    if args.list:
        for r in out:
            if r["cat"] == args.list:
                leak = f"  누출={r['leaks']}" if r["leaks"] else ""
                print(f"{r['ntt_id']} | {r['sub']}{leak}")
        return

    print(f"=== 파싱 품질 funnel (총 메타 {total}, 기대 {expected_total}) ===")
    for c in CAT_ORDER:
        v = cat.get(c, 0)
        if not v:
            continue
        pct = 100 * v / total
        bar = "█" * int(pct / 2)
        print(f"  {v:5} ({pct:4.1f}%) {bar:<26} {CAT_LABEL[c]}")
    good = cat["ok"]
    print(f"--- 기대 대비 정상률: {good}/{expected_total} = "
          f"{100 * good / max(1, expected_total):.1f}%  "
          f"(누출+실패+무PDF+이미지 = {expected_total - good})")

    if args.baseline and REPORT.exists():
        prev = json.loads(REPORT.read_text(encoding="utf-8")).get("cat", {})
        print("--- 직전 대비 diff ---")
        for c in CAT_ORDER:
            d = cat.get(c, 0) - prev.get(c, 0)
            if d:
                print(f"  {CAT_LABEL[c]}: {d:+d}")

    payload = {"total": total, "expected": expected_total, "cat": dict(cat)}
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(
            json.dumps({"summary": payload, "rows": out}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"리포트 → {args.json}")


if __name__ == "__main__":
    main()
