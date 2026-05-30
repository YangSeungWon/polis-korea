"""선거 메타 레지스트리 loader — data/elections/*.json read-only helper.

Phase 1에서 분리한 메타 파일을 읽는 단일 진입점. build_polls·scrape_nesdc·
fetch_nec_roster·fetch_nec_results 등이 import해서 사용 (Phase 3~5에서 마이그레이션).

스키마 — data/elections/index.json:
  { "active": ["9th-local-2026", ...], "archive": [...] }

스키마 — data/elections/{id}.json (active 선거):
  {
    "id": "9th-local-2026",
    "name": "제9회 전국동시지방선거",
    "type": "local",
    "date": "2026-06-03",
    "blackout": {"start": "...", "end": "..."},
    "nesdc": {"gubun": "VT026", "csv": "..."},
    "nec": {"sg_id": "20260603", "roster": "..."},
    "offices": [{"level": "광역단체장", "sg_typecode": "3", ...}, ...],
    "party_canon": {...},
    "sido_merge": [{"canonical": "전남광주특별시", "merge_from": [...]}],
    "candidates_overrides": "data/elections/9th-local-2026-candidates.json"
  }

사용:
  from election_meta import load_active, load_election, current_election
  metas = load_active()  # list[dict]
  m = load_election("9th-local-2026")  # dict
  cur = current_election()  # 가장 가까운 active election (오늘 기준)
"""
from __future__ import annotations
import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ELECTIONS_DIR = ROOT / "data/elections"
INDEX_PATH = ELECTIONS_DIR / "index.json"


@lru_cache(maxsize=1)
def load_index() -> dict:
    """data/elections/index.json — {active: [ids], archive: [ids]}."""
    if not INDEX_PATH.exists():
        return {"active": [], "archive": []}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=32)
def load_election(election_id: str) -> dict:
    """선거 메타 dict. 없으면 빈 dict."""
    p = ELECTIONS_DIR / f"{election_id}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_active() -> list[dict]:
    """active 선거들의 메타 list. index 순서 유지."""
    idx = load_index()
    return [m for m in (load_election(i) for i in idx.get("active", [])) if m]


def load_archive(election_id: str = "") -> list[dict] | dict:
    """archive 선거 메타.
    election_id 주면 단건, 빈 string이면 list (메타 파일 없는 archive id는 제외).
    """
    if election_id:
        return load_election(election_id)
    idx = load_index()
    return [m for m in (load_election(i) for i in idx.get("archive", [])) if m]


def current_election(today: Optional[date] = None) -> dict:
    """오늘 기준 가장 가까운 active 선거. 동률이면 첫 active."""
    today = today or date.today()
    actives = load_active()
    if not actives:
        return {}
    # 미래 선거 우선. 모두 과거면 가장 최근.
    def _delta(m):
        try:
            d = date.fromisoformat(m["date"])
            return (d - today).days
        except Exception:
            return 99999
    future = [m for m in actives if _delta(m) >= 0]
    if future:
        return min(future, key=_delta)
    return max(actives, key=_delta)


def get_office(meta: dict, level: str) -> Optional[dict]:
    """meta.offices에서 level('광역단체장' 등) 매칭 office."""
    for o in meta.get("offices", []):
        if o.get("level") == level:
            return o
    return None


def sido_merge_map(meta: dict) -> dict[str, str]:
    """sido_merge 정의 → {alias: canonical} dict.
    예: {'광주광역시': '전남광주특별시', '전라남도': '전남광주특별시'}.
    """
    out = {}
    for m in meta.get("sido_merge", []):
        canonical = m.get("canonical", "")
        for alias in m.get("merge_from", []):
            out[alias] = canonical
    return out


def canon_sido(meta: dict, sido: str) -> str:
    """sido_merge 적용 후 canonical sido. 매핑 없으면 그대로."""
    return sido_merge_map(meta).get(sido, sido)


def is_blackout(meta: dict, now: Optional[datetime] = None) -> bool:
    """공표금지 기간 활성 여부."""
    now = now or datetime.now().astimezone()
    b = meta.get("blackout", {})
    try:
        start = datetime.fromisoformat(b["start"])
        end = datetime.fromisoformat(b["end"])
        return start <= now <= end
    except Exception:
        return False


@lru_cache(maxsize=8)
def load_candidates_overrides(election_id: str) -> dict[str, str]:
    """{id}-candidates.json → {후보명: 정당} flat dict.
    자체조사 PDF·정당 미명기 후보의 정당 매핑 fallback.

    파일 스키마: { "더불어민주당": ["오중기", ...], "국민의힘": [...], ... }
    """
    meta = load_election(election_id)
    path_str = meta.get("candidates_overrides", "")
    if not path_str:
        return {}
    p = ROOT / path_str
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for party, names in raw.items():
        if party.startswith("_") or not isinstance(names, list):
            continue
        for nm in names:
            out[nm] = party
    return out


def get_byelection_district(meta: dict, district: str) -> dict:
    """재보궐 선거 메타의 districts[district] 반환 (latlng + candidates).
    9th-byelection-2026.json 등에 사용.
    """
    return meta.get("districts", {}).get(district, {})


def candidate_party_from_district(meta: dict, district: str, name: str) -> str:
    """재보궐 선거구의 후보 정당. 없으면 빈 string."""
    d = get_byelection_district(meta, district)
    return d.get("candidates", {}).get(name, "")


# CLI 디버깅
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="특정 선거 메타 출력")
    ap.add_argument("--current", action="store_true", help="현재 선거")
    ap.add_argument("--list", action="store_true", help="active+archive 전체")
    args = ap.parse_args()
    if args.list or (not args.id and not args.current):
        idx = load_index()
        print(f"active ({len(idx.get('active', []))}):")
        for m in load_active():
            print(f"  {m['id']:25s} {m['name']:30s} {m.get('date', '?')}")
        print(f"\narchive ({len(idx.get('archive', []))}):")
        for aid in idx.get("archive", []):
            m = load_election(aid)
            if m:
                print(f"  {m['id']:25s} {m['name']:30s} {m.get('date', '?')}")
            else:
                print(f"  {aid:25s} (메타 파일 미작성)")
    elif args.current:
        m = current_election()
        print(json.dumps(m, ensure_ascii=False, indent=2))
    elif args.id:
        m = load_election(args.id)
        print(json.dumps(m, ensure_ascii=False, indent=2))
