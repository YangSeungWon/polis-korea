"""링크 그래프 — 개수가 아니라 **연결성**.

'링크가 몇 개 있나'는 답이 아니다. 물어야 할 것은 '사용자가 어느 entity에서
시작해도 다른 축으로 계속 이동할 수 있는가'다.

정적 HTML의 href만 본다. JS 렌더 링크는 크롤러가 못 보고, 상호작용 전엔 사용자도
못 본다(archive 당선인 섹션이 그랬다 — 3,967명 필터 UI라 링크가 0이었다).

**false link 0을 unresolved 감소보다 우선한다.** 동명이인·동명 시군구를 억지로
이으면 틀린 사람·틀린 지역으로 보내는 링크가 된다. 그래서 KPI를 넷으로 나눈다:
  linked                  이었다
  ambiguous               후보가 여럿이라 못 정함 (동명 시군구 등)
  unresolved              색인에 없음 (옛 회차 등)
  intentionally_unlinked  이을 수 있지만 안 잇기로 한 것 (무소속·미등록 정당)

실행: .venv/bin/python tests/test_link_graph.py
"""
from __future__ import annotations
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def links_of(p: Path, prefix: str) -> set:
    t = p.read_text(encoding="utf-8")
    return set(re.findall(rf'href="({re.escape(prefix)}[^"#?]*)', t))


def first(pat: str) -> Path | None:
    it = sorted(ROOT.glob(pat))
    return it[0] if it else None


def main() -> int:
    # ── 대표 경로: 각 홉이 **정적** 링크만으로 이어지는가 ────────────────────
    print("\n[경로] 정적 HTML 링크만으로 이어지는가")

    from urllib.parse import unquote

    def resolve(u: str) -> Path:
        rel = unquote(u).lstrip("/")
        return ROOT / (rel + "index.html" if rel.endswith("/") else rel)

    def hop(srcs, prefix: str, label: str) -> list:
        """다음 홉으로 갈 수 있는 페이지들. 한 노드에 링크가 없는 건 결함이 아닐 수
        있다 — 개혁신당은 시군구 1위가 없어 '지역 기반' 섹션이 정당하게 없다.
        물어야 할 것은 '이 축에서 다음 축으로 갈 길이 **있는가**'다."""
        if isinstance(srcs, Path):
            srcs = [srcs]
        out, n = [], 0
        for src in srcs[:12]:
            for u in sorted(links_of(src, prefix)):
                f = resolve(u)
                if f.exists():
                    out.append(f)
                    n += 1
        ck(f"{label}", bool(out),
           f"{len(srcs)}개 출발점 어디서도 {prefix}로 못 감")
        # 중복 제거하되 순서 유지 — 다음 홉의 출발점 후보들
        seen, uniq = set(), []
        for f in out:
            if f not in seen:
                seen.add(f); uniq.append(f)
        return uniq

    # 선거 → 인물 → 정당 → 지역 → 선거
    a = ROOT / "archive/21st-pres-2025/index.html"
    ck("출발: 대선 archive", a.exists())
    if a.exists():
        person = hop(a, "/person/", "선거 → 인물")
        party = hop(a, "/party/", "선거 → 정당")
        if party:
            reg = hop(party, "/region/", "정당 → 지역")
            if reg:
                hop(reg, "/archive/", "지역 → 선거  (순환 완성)")
                hop(reg, "/person/", "지역 → 인물")
        if person:
            hop(person, "/archive/", "인물 → 선거")
            hop(person, "/party/", "인물 → 정당")
            hop(person, "/region/", "인물 → 지역")

    # ── 고아: 어디에서도 링크되지 않는 entity가 있는가 ──────────────────────
    print("\n[고아] 들어오는 링크가 있는가")
    inbound_region = set()
    for p in list(ROOT.glob("archive/*/index.html")) + list(ROOT.glob("person/*/index.html")) \
            + list(ROOT.glob("party/*/index.html")) + [ROOT / "region/index.html"]:
        if p.exists():
            inbound_region |= links_of(p, "/region/")
    from urllib.parse import unquote
    have = {f"/region/{d.name}/" for d in (ROOT / "region").iterdir()
            if d.is_dir() and (d / "index.html").exists()}
    orphan_rg = have - {unquote(u) for u in inbound_region}
    ck(f"지역 {len(have)}곳 전부 들어오는 링크 있음", not orphan_rg, str(sorted(orphan_rg)[:3]))

    # ── KPI: linked / ambiguous / unresolved / intentionally_unlinked ───────
    print("\n[KPI] 이은 것 · 못 이은 것 · 안 이은 것")
    sys.path.insert(0, str(ROOT / "scripts/build"))
    from build_region_pages import collect, person_href
    reg_registry = set(json.loads(
        (ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"])

    k = Counter()
    for rows in collect().values():
        for r in rows:
            if len(rows) < 3:
                continue
            # 인물
            if person_href(r["eid"], r.get("tc") or "", r.get("place") or "", r.get("name") or ""):
                k["person_linked"] += 1
            else:
                k["person_unresolved"] += 1
            # 정당 — 무소속·미등록은 '안 이은 것'이지 '못 이은 것'이 아니다
            pty = r.get("party") or ""
            if pty == "무소속":
                k["party_intentionally_unlinked"] += 1
            elif pty in reg_registry:
                k["party_linked"] += 1
            else:
                k["party_unresolved"] += 1
    tot_p = k["person_linked"] + k["person_unresolved"]
    print(f"    인물  linked {k['person_linked']:,} · unresolved {k['person_unresolved']:,}"
          f"  ({k['person_linked'] / tot_p * 100:.0f}%)")
    print(f"    정당  linked {k['party_linked']:,} · 의도적 미연결 {k['party_intentionally_unlinked']:,}"
          f" · unresolved {k['party_unresolved']:,}")

    # 링크가 있다면 반드시 실재해야 한다 — false link 0이 목표다.
    #
    # /region/을 함께 본다. 모시↔구를 잇는 링크가 생기면서 by_region에는 있지만
    # MIN_ROUNDS 미달로 페이지가 없는 구까지 링크해 404 18개를 만들었는데, 이
    # 검사가 /person/·/party/만 보고 있어 게이트를 그냥 통과했다.
    #
    # 앞 200쪽만 보던 것도 걷어낸다. 356쪽을 다 읽어도 순식간이고, 잘라 놓으면
    # 뒤쪽 시도(충청·전라·경상)의 링크는 아무도 안 본다 — 실제로 죽은 링크가
    # 대전시·마산시처럼 정렬 뒤쪽에 몰려 있었다.
    dead = []
    for p in sorted(ROOT.glob("region/*/index.html")):
        for u in (links_of(p, "/person/") | links_of(p, "/party/")
                  | links_of(p, "/region/")):
            rel = unquote(u).lstrip("/")
            if not (ROOT / (rel + "index.html" if rel.endswith("/") else rel)).exists():
                dead.append(f"{p.parent.name}: {u}")
    ck("지역 페이지의 인물·정당·지역 링크가 전부 실재 (false link 0)",
       not dead, f"{len(dead)}개 — {dead[:3]}")

    # 동명 시군구는 잇지 않는다 — 이었다면 틀린 지역으로 보내는 링크다
    from build_person_pages import region_slug_index
    idx = region_slug_index()
    dupes = ["중구", "서구", "남구", "북구", "동구"]
    linked_dupes = [d for d in dupes if d in idx]
    ck("동명 시군구는 잇지 않음", not linked_dupes, str(linked_dupes))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
