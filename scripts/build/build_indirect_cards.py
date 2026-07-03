#!/usr/bin/env python3
"""간접선거(체육관 선거) 결과 카드 PNG 생성 — 타임라인 호버 썸네일용.

8~12대 대선(유신·전두환기 통일주체국민회의/대통령선거인단 간선)은 득표 지도가 없어
build_og_maps가 스킵 → 타임라인 호버가 블랭크. 대신 **선거인단 dot-grid**(각 점=선거인,
당색 비례)로 만장일치에 가까운 간선의 성격을 정직히 드러내는 카드를 생성한다.

data/results/*.json의 _meta.indirect_election 플래그로 간선 판별. 출력:
  og/maps/{slug}/sido1.png (대선 호버 view) + dorling.png (폴백) — 동일 카드.

의존: pillow + 한글 TTF(나눔). 사용: python scripts/build/build_indirect_cards.py
"""
from __future__ import annotations
import glob
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"
MAPS = ROOT / "og/maps"

FONT_B = "/usr/share/fonts/truetype/nanum/NanumSquareRoundB.ttf"
FONT_EB = "/usr/share/fonts/truetype/nanum/NanumSquareRoundEB.ttf"

# 당색 — assets/parties.js PARTY_COLORS 발췌(간선 관련 정당).
PARTY_COLOR = {
    "민주공화당": "#835B38", "민주정의당": "#0A84E9", "무소속": "#888888",
    "민주한국당": "#ED2939", "한국국민당": "#498C00", "민권당": "#4CA459",
}
INK = "#1a1c22"
MUTE = "#7a828e"
CARD = "#ffffff"
GRID_EMPTY = "#e3e6ec"

W, H = 600, 500
COLS, DOTS = 24, 240   # 24열, 총 240점(각 ≈0.42%)


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _font(path, sz):
    try:
        return ImageFont.truetype(path, sz)
    except Exception:
        return ImageFont.load_default()


def render_card(slug: str, meta: dict, cands: list) -> Image.Image:
    m = re.match(r"(\d+)(?:st|nd|rd|th)-pres-(\d{4})", slug)
    nth, year = (m.group(1), m.group(2)) if m else ("", "")
    body = meta.get("indirect_election", "간접선거")
    organ = "대통령선거인단" if "선거인단" in body else "통일주체국민회의"
    win = cands[0]

    # 후보별 dot 수(비례, 합=DOTS; 나머지는 승자에게).
    alloc = []
    used = 0
    for c in cands:
        n = round(c.get("pct", 0) / 100 * DOTS)
        alloc.append([c, n]); used += n
    if alloc:
        alloc[0][1] += DOTS - used   # 잔여 보정
    seq = []
    for c, n in alloc:
        col = _hex(PARTY_COLOR.get(c.get("party", ""), "#9aa0aa"))
        seq += [col] * max(0, n)
    seq = seq[:DOTS] + [_hex(GRID_EMPTY[1:])] * max(0, DOTS - len(seq))

    img = Image.new("RGB", (W, H), _hex(CARD))
    d = ImageDraw.Draw(img)
    fb = _font(FONT_B, 30); feb = _font(FONT_B, 40)   # EB 미설치 → B 사용(load_default는 한글 못 그림)
    fsm = _font(FONT_B, 24); ftiny = _font(FONT_B, 22)

    pad = 34
    # 헤더
    d.text((pad, 30), f"제{nth}대 대통령 선거", font=fb, fill=_hex(INK))
    # '간접선거' 태그
    tag = "간접선거"
    tw = d.textlength(tag, font=ftiny)
    d.rounded_rectangle((W - pad - tw - 22, 34, W - pad, 34 + 34), 8, fill=_hex("#efe1d0"))
    d.text((W - pad - tw - 11, 39), tag, font=ftiny, fill=_hex("#8a5a1f"))
    d.text((pad, 72), organ, font=fsm, fill=_hex(MUTE))

    # dot grid
    gx, gy = pad, 128
    r, gap = 7, 5
    step = 2 * r + gap
    for i, col in enumerate(seq):
        cx = gx + (i % COLS) * step
        cy = gy + (i // COLS) * step
        d.ellipse((cx, cy, cx + 2 * r, cy + 2 * r), fill=col)
    rows = (DOTS + COLS - 1) // COLS
    gbot = gy + rows * step

    # 승자 라인
    y = gbot + 22
    wc = _hex(PARTY_COLOR.get(win.get("party", ""), "#9aa0aa"))
    d.ellipse((pad, y + 12, pad + 22, y + 34), fill=wc)
    d.text((pad + 34, y), win.get("name", ""), font=feb, fill=_hex(INK))
    nx = pad + 34 + d.textlength(win.get("name", ""), font=feb) + 14
    d.text((nx, y + 12), win.get("party", ""), font=fsm, fill=wc)
    votes = f"{win.get('votes', 0):,}표 · {win.get('pct', 0)}%"
    d.text((pad, y + 54), votes, font=fsm, fill=_hex(MUTE))
    return img


def main():
    made = 0
    for fp in sorted(glob.glob(str(RESULTS / "*.json"))):
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        meta = d.get("_meta", {})
        if not meta.get("indirect_election"):
            continue
        slug = Path(fp).stem
        races = d.get("races", [])
        cands = races[0].get("candidates", []) if races else []
        if not cands:
            continue
        cands = sorted(cands, key=lambda c: -c.get("pct", 0))
        img = render_card(slug, meta, cands)
        outdir = MAPS / slug
        outdir.mkdir(parents=True, exist_ok=True)
        for view in ("sido1", "dorling"):
            img.save(outdir / f"{view}.png")
        made += 1
        print(f"  ✓ {slug}: {cands[0]['name']} {cands[0]['pct']}% ({meta['indirect_election']})")
    print(f"간접선거 카드 {made}개 생성 → og/maps/*/{{sido1,dorling}}.png")


if __name__ == "__main__":
    main()
