"""선거 결과 → 정적 HTML 표. archive와 history가 같이 쓴다.

두 생성기가 같은 표를 낸다. archive는 회차 단위로, history는 (회차 × 직위) 단위로 —
축이 하나 다를 뿐 읽는 데이터도 만드는 표도 같다. 각자 만들면 한쪽만 고쳐지고
어긋난다(이 저장소에서 뷰 표가 그렇게 네 벌이 됐다).

⚠️ 큰 회차는 시군구 결과가 **별도 청크**에 있다(_meta.chunked → {eid}.sigungu.json).
본 파일만 읽으면 21대 대선 races가 18개(전국+시도)뿐이라 표가 통째로 빈다.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "data" / "results"

TC_LABEL = {"1": "대통령", "2": "국회의원", "3": "광역단체장", "4": "기초단체장",
            "5": "광역의원", "6": "기초의원", "7": "비례대표", "11": "교육감"}


def _esc(x) -> str:
    return (str(x if x is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _pct(v) -> str:
    return f"{v:.1f}%" if isinstance(v, (int, float)) else "—"


def load_races(eid: str) -> list:
    """본 파일 + 시군구 청크를 합쳐 돌려준다."""
    rp = RESULTS_DIR / f"{eid}.json"
    if not rp.is_file():
        return []
    try:
        doc = json.loads(rp.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    races = list(doc.get("races") or [])
    if (doc.get("_meta") or {}).get("chunked"):
        cp = RESULTS_DIR / f"{eid}.sigungu.json"
        if cp.is_file():
            try:
                races += (json.loads(cp.read_text(encoding="utf-8")) or {}).get("races") or []
            except Exception:
                pass
    return races


def turnout_of(r: dict) -> str:
    el, vo = r.get("electors"), r.get("voters")
    return _pct(round(vo / el * 100, 1)) if el and vo else "—"


def winner_rows(races: list, tc: str, scope: str, *, place_cols, link) -> list[list[str]]:
    """(tc, scope) race들 → 표 행. link(kind, place, name)이 링크 HTML을 준다."""
    rows = []
    for r in races:
        if r.get("sg_typecode") != tc or r.get("scope") != scope:
            continue
        cs = sorted(r.get("candidates") or [], key=lambda c: -(c.get("votes") or 0))
        if not cs:
            continue
        c = next((x for x in cs if x.get("won")), cs[0])
        place = r.get("sigungu") or r.get("district") or r.get("sido") or ""
        cols = [_esc(r.get(k) or "") for k in place_cols]
        rows.append(cols + [link("person", place, c.get("name")),
                            link("party", "", c.get("party")),
                            _pct(c.get("pct")), turnout_of(r)])
    return rows


def table_html(sec_id: str, cap: str, head: list[str], rows: list[list[str]],
               unit: str = "곳") -> str:
    """표 한 장. 행이 없으면 빈 문자열 — 빈 표를 만들지 않는다.

    unit은 캡션의 세는 말이다. 대부분 지역을 세지만(곳), 선거를 세는 표도 있다(번).
    """
    if not rows:
        return ""
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return (f'\n  <section class="ar-section" id="{sec_id}">\n'
            f'    <h2 class="ar-section-title">{cap}</h2>\n'
            f'    <div class="pp-scroll">'
            f'<table class="pp-static"><caption>{cap} — {len(rows)}{unit}</caption>'
            f'<thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>\n'
            f'  </section>\n')


def png_size(path: Path) -> tuple[int, int] | None:
    """PNG 폭·높이를 헤더에서 직접 읽는다. 의존성 없음.

    처음엔 Pillow를 썼다가 CI에서 ModuleNotFoundError로 죽었다 — 로컬엔 다른 패키지의
    의존성으로 깔려 있었고 requirements.txt엔 없었다. 폭·높이 두 값 때문에 이미지
    라이브러리를 빌드 의존성으로 만드는 건 과하다.

    PNG는 시그니처 8바이트 + IHDR 길이 4 + 타입 4 다음에 폭·높이가 big-endian
    4바이트씩이다(고정 오프셋 16·20). 스펙이 바뀔 일이 없다.
    """
    try:
        with path.open("rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))


def caption(key: str, m: dict) -> str:
    """그림 한 장의 캡션. **여기가 유일한 조립 자리다.**

    구분자는 ' · '다. 섹션 제목에 이미 em대시가 든 것이 있어('기초의원 비례 —
    시·군·구별 표심') 같은 기호로 모드를 이으면 '— … —'가 되어 어디까지가 제목인지
    안 보인다.

    검사(tests/test_view_keys.py)도 이 함수를 부른다. 검사가 제 나름대로 다시
    조립하면 그것도 사본이라, 형식을 바꿀 때 검사만 빨개진다 — 실제로 그랬다.
    검사가 볼 것은 '페이지의 글이 매니페스트에서 나왔는가'지 '형식이 내 취향인가'가
    아니다.
    """
    return " · ".join(x for x in (m.get("title"), m.get("label")) if x) or key


def fig(eid: str, key: str, m: dict, w: int, h: int, title: str,
        base: str = "/og/maps") -> str:
    """<figure> 한 장. **글이 그림과 같은 출처에서 나온다.**

    label은 캡처가 실제로 누른 토글 버튼의 글씨고, title·desc는 그 지도가 놓인
    섹션의 제목과 설명이다(data/map_captures.json). 손으로 쓴 문구를 섞으면
    다시 어긋난다 — 옛 view_meta()는 모르는 키에 키 자신을 라벨로 돌려줘서
    'sgg-prop' 같은 슬러그가 한글 캡션 자리에 찍혀도 아무도 몰랐다.
    """
    cap = caption(key, m)
    desc = (m.get("desc") or "").strip()
    alt = _esc(" — ".join(x for x in (" ".join(y for y in (title, cap) if y), desc) if x))
    return (f'<figure class="map-fig" id="{_esc(key)}">'
            f'<img src="{base}/{_esc(eid)}/{_esc(key)}.png" alt="{alt}" '
            f'width="{w}" height="{h}" loading="lazy" decoding="async">'
            f'<figcaption>{_esc(cap)}</figcaption></figure>')
