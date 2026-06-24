#!/usr/bin/env python3
"""전국 여론조사 PDF의 '응답자 특성별 후보(차기주자) 지지도' → 성×연령 추출.

정당지지(extract_party_demographics)와 표 구조 동일 — 성별/연령/성연령 행 × 후보 열.
열이 '정당'이 아니라 '인물(차기 대선주자)'이라는 점만 달라, 위치기반 파서(parse_pdf)를
그대로 재사용하고 로스터를 후보로, party_of를 후보→정당 맵으로 바꾼다.

차기주자 선호는 선거 비종속 상시 신호 → 트래커 '차기 대선주자'에 성연령 차원으로 붙는다
(세대·성별로 다른 대권주자 — 이대남의 이준석 등).

로스터: 큐레이트한 실제 차기주자 명단(CAND, 외부 고정 — 파싱 candidate 필드는 잡음 많아
빈도 로스터가 오염됨). 정당(색)은 CAND 맵. 위치기반 파서에 known=로스터로 넘겨 지역·정당
표 오매칭 차단(헤더에 실제 후보 ≥2 요구).

출력: data/raw/parsed/cand_demographics.json = { ntt_id: {성별,연령,성연령}, row={name,party,pct} }

사용:
  python scripts/parse/extract_cand_demographics.py --pdf <경로>   # 단건
  python scripts/parse/extract_cand_demographics.py                # 전량(캐시·재개)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_party_demographics as P   # parse_pdf·_SPECIAL 재사용  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW_PDF = ROOT / "data/raw/pdf"
PARSED = ROOT / "data/raw/parsed"

# 큐레이트한 차기주자(2016~2026) 명단 → 정당(색). 파싱된 candidate 필드는 잡음('가중치'·
# '간다' 등)이 많아 빈도 로스터가 오염됨 → 실제 인물만 외부 명단으로 고정(정당 registry처럼).
# 정당 변화 인물은 가장 알려진/최종 정당으로(색 근사). 위치기반 파서가 이 이름들로 표를 식별.
CAND = {
    # 더불어민주당(및 전신·민주계)
    "이재명": "더불어민주당", "문재인": "더불어민주당", "이낙연": "더불어민주당",
    "안희정": "더불어민주당", "박원순": "더불어민주당", "김부겸": "더불어민주당",
    "정세균": "더불어민주당", "김경수": "더불어민주당", "추미애": "더불어민주당",
    "임종석": "더불어민주당", "박용진": "더불어민주당", "송영길": "더불어민주당",
    "김두관": "더불어민주당", "양승조": "더불어민주당", "우상호": "더불어민주당",
    "전해철": "더불어민주당", "이광재": "더불어민주당", "최문순": "더불어민주당",
    "김동연": "더불어민주당", "정동영": "더불어민주당",
    # 국민의힘(및 전신 자유한국당·미래통합당·바른정당·국민의당)
    "윤석열": "국민의힘", "홍준표": "국민의힘", "황교안": "국민의힘", "오세훈": "국민의힘",
    "한동훈": "국민의힘", "원희룡": "국민의힘", "나경원": "국민의힘", "김문수": "국민의힘",
    "안철수": "국민의힘", "유승민": "국민의힘", "김기현": "국민의힘", "김태호": "국민의힘",
    "김진태": "국민의힘", "권성동": "국민의힘", "하태경": "국민의힘", "윤희숙": "국민의힘",
    "남경필": "국민의힘", "안상수": "국민의힘",
    # 기타
    "이준석": "개혁신당", "심상정": "정의당", "조국": "조국혁신당",
    "반기문": "무소속", "한덕수": "무소속", "손학규": "무소속",
}


def build_roster():
    """큐레이트 명단 → (v2c, variants, party_of). 후보=identity, 정당=CAND 맵."""
    roster = set(CAND)
    v2c = {nm: nm for nm in roster}
    for s in P._SPECIAL:
        v2c.setdefault(s, s)
    variants = sorted(set(list(roster) + list(P._SPECIAL)), key=len, reverse=True)
    def party_of(nm):
        return "" if nm in P._SPECIAL else CAND.get(nm, "")
    return v2c, variants, party_of, roster


def _iter_cand_polls():
    """다자(≥4 CAND 후보) 차기주자 질문 든 폴만 — 양자·소수·비후보 폴 건너뛰어 스캔 폭 축소."""
    roster = set(CAND)
    seen = set()
    for f in PARSED.glob("*.json"):
        if f.name.startswith("."):
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        rich = any(q.get("election_office") == "후보지지"
                   and len({c.get("name") for c in (q.get("candidates") or [])} & roster) >= 4
                   for q in d.get("questions", []))
        if rich:
            stem = f.name[:-5]
            if stem not in seen:
                seen.add(stem)
                yield str(d.get("ntt_id") or stem.split("_")[0]), stem


def main():
    v2c, variants, party_of, roster = build_roster()
    print(f"후보 로스터 {len(roster)}명 (큐레이트)", flush=True)

    if len(sys.argv) >= 3 and sys.argv[1] == "--pdf":
        res = P.parse_pdf(Path(sys.argv[2]), v2c, variants, party_of, roster)
        print(json.dumps(res, ensure_ascii=False, indent=2) if res else "추출 실패")
        return

    cache_path = PARSED / ".cand_demo_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    out, ok = {}, 0
    todo = list(_iter_cand_polls())
    print(f"후보지지 폴 {len(todo)}건 — 성×연령 cross-tab 스캔...", flush=True)
    for i, (ntt, stem) in enumerate(todo):
        if stem in cache:
            rows = cache[stem]
        else:
            pdfs = list(RAW_PDF.glob(stem + ".*"))
            rows = P.parse_pdf(pdfs[0], v2c, variants, party_of, roster) if pdfs else None
            cache[stem] = rows
        if rows:
            out[ntt] = rows
            ok += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(todo)}, 추출 {ok}", flush=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    dst = PARSED / "cand_demographics.json"
    dst.write_text(json.dumps(out, ensure_ascii=False))
    g = sum(1 for v in out.values() if v.get("성연령", {}).get("남성"))
    print(f"차기주자: {len(todo)}건 중 추출 {ok}건 (성×연령 그리드 {g}건) → {dst.name}")


if __name__ == "__main__":
    main()
