"""파서 골든 회귀 테스트 — parse_pdf가 까다로운 케이스를 계속 맞히는지 검증.

이번에 튠한 어려운 양식들(이름이 정당조각과 겹침·직책 설명·무소속·질문조각 노이즈)을
고정해, parse_pdf 리팩토링/수정 시 회귀를 잡는다.

의존성 없음 (pytest 불필요):
    .venv/bin/python tests/test_parser_golden.py
PDF는 data/raw/pdf/ (gitignore) — 없는 케이스는 SKIP. 골든 값은 이 파일에 박제.
실패 시 exit 1.
"""
from __future__ import annotations
import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from parse_pdf import parse_pdf  # noqa: E402

# 케이스: ntt_id → {desc, must_have: [(이름, 정당), ...]}
# must_have = 국회의원후보 표(들)에 반드시 등장해야 하는 (이름, 정당) 쌍.
GOLDEN = {
    "18771": {  # 평택을 에이스 — "정당 후보 이름", 조국(조국혁신당)·황교안(자유와혁신)
        "desc": "평택시을 에이스리서치 5자대결",
        "must_have": [("김용남", "더불어민주당"), ("유의동", "국민의힘"),
                      ("조국", "조국혁신당"), ("김재연", "진보당"), ("황교안", "자유와혁신")],
    },
    "18680": {  # 평택을 한국갤럽 — "조국 현 조국혁신당 당대표" (직책 마커 양식)
        "desc": "평택시을 한국갤럽 5/13",
        "must_have": [("김용남", "더불어민주당"), ("조국", "조국혁신당"), ("황교안", "자유와혁신")],
    },
    "18761": {  # 평택을 한국갤럽 — "조국혁신당 조국" (직책 없는 단순 양식)
        "desc": "평택시을 한국갤럽 5/17",
        "must_have": [("조국", "조국혁신당"), ("김재연", "진보당")],
    },
    "18441": {  # 부산북구갑 한국리서치 — "무소속 한동훈 전 국민의힘 대표" (직책의 국민의힘 오인 방지)
        "desc": "부산 북구갑 한국리서치",
        "must_have": [("하정우", "더불어민주당"), ("박민식", "국민의힘"), ("한동훈", "무소속")],
    },
}

# 국회의원후보 표의 후보 이름으로 절대 나오면 안 되는 노이즈
# (정당조각·직책·질문문 조각·선거구명. "무소속"은 정당이지 이름 아님)
NOISE_NAMES = {
    "낫다고조", "평택시후", "대표", "조국현당", "보조국", "후보조국",
    "실시되어", "인천광역", "연수구갑", "무소속", "양자대결", "합계조사", "보궐선거",
}


def real_candidates(pdf_path: Path) -> list[tuple[str, str]]:
    """국회의원후보 표의 (이름, 정당) — 둘 다 있는 것만 (build가 쓰는 'real' 기준)."""
    res = parse_pdf(pdf_path)
    out = []
    for q in res.get("questions", []):
        if q.get("election_office") != "국회의원후보":
            continue
        for c in q.get("candidates", []):
            if c.get("name") and c.get("party"):
                out.append((c["name"], c["party"]))
    return out


def run() -> int:
    fails, skipped, passed = [], [], 0
    for nid, g in GOLDEN.items():
        pdfs = glob.glob(str(ROOT / f"data/raw/pdf/{nid}_*.pdf"))
        if not pdfs:
            skipped.append(f"{nid} ({g['desc']})")
            continue
        cands = real_candidates(Path(pdfs[0]))
        names = {n for n, _ in cands}
        case_fail = []
        for pair in g["must_have"]:
            if pair not in cands:
                case_fail.append(f"누락 {pair}")
        bad = names & NOISE_NAMES
        if bad:
            case_fail.append(f"노이즈 후보명 {sorted(bad)}")
        if case_fail:
            fails.append(f"  ✗ {nid} {g['desc']}: " + "; ".join(case_fail)
                         + f"\n      실제 후보: {sorted(set(cands))}")
        else:
            passed += 1
            print(f"  ✓ {nid} {g['desc']} ({len(set(cands))}명)")

    for s in skipped:
        print(f"  - SKIP {s} (PDF 없음)")
    print(f"\n통과 {passed} / 실패 {len(fails)} / 스킵 {len(skipped)}")
    if fails:
        print("실패:")
        print("\n".join(fails))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
