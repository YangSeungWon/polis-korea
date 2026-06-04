"""golden test set 생성 — 양식별 대표 ntt의 현재 parse 결과를 tests/golden/ 에 저장.

회귀 테스트 baseline. parse 룰 변경 후 `tests/test_golden.py` 돌리면 diff 보임.
한 번 검증 후엔 expected와 다른 결과면 fail.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "parse"))


ROOT = Path(__file__).resolve().parents[2]
GRIDS = ROOT / "data/raw/grids"
GOLDEN = ROOT / "tests/golden"
sys.path.insert(0, str(ROOT / "scripts"))
from parse_pdf_v2 import parse_from_grids  # type: ignore

# 양식별 대표 ntt — 다양한 PDF 양식 + 다양한 office + 이전 잡음 fix 검증용
GOLDEN_NTTS = {
    # 양식별 정상 다자대결
    "17254": "조원씨앤아이 — 정읍 다자대결 (wrap 후보명: 안수용/정도진)",
    "16317": "리얼미터 — 광주 정당지지 (multi-row header + /구분자)",
    "16708": "에이스 — 포항 차기시장 (title row skip 검증)",
    "17034": "비전코리아 — 공주 정당지지·후보지지",
    "17896": "한국리서치 — 제주도지사 다자대결·당내경선·양자대결",
    "18274": "에이스 — 양구군수 (시군구 라벨 침투 케이스)",
    "18513": "에이스 — 동해시장 (3 후보 다자대결 + 강원지사)",
    "16788": "데일리리서치 — 장성군수 (격자 2분리 케이스, 일부만 추출)",
    # 정상 단일후보 폴
    "18751": "케이스탯 — 증평군수 단일 (이재영)",
    "17283": "경남통계 — 진주시장 (조규일)",
}


def main():
    GOLDEN.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for ntt, note in GOLDEN_NTTS.items():
        grid_files = list(GRIDS.glob(f"{ntt}_*.json"))
        if not grid_files:
            print(f"  ! {ntt}: 격자 cache 없음 ({note})", file=sys.stderr)
            skipped += 1
            continue
        # 한 ntt에 여러 PDF (질문지·결과보고서). parse 결과 풍부한 쪽 선택.
        best = None
        for gf in grid_files:
            g = json.load(open(gf, encoding="utf-8"))
            r = parse_from_grids(g)
            score = sum(len(q.get("candidates", [])) for q in r.get("questions", []))
            if best is None or score > best[0]:
                best = (score, g, r, gf)
        _, grids, result, _ = best
        out = {
            "ntt_id": ntt,
            "source_pdf": grids.get("source_pdf", ""),
            "note": note,
            "expected_questions": result.get("questions", []),
        }
        out_path = GOLDEN / f"{ntt}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        n_q = len(out["expected_questions"])
        n_c = sum(len(q.get("candidates", [])) for q in out["expected_questions"])
        print(f"  OK {ntt}: {n_q} questions, {n_c} candidates — {note}")
        written += 1
    print(f"\n완료: {written} golden written, {skipped} skipped")


if __name__ == "__main__":
    main()
