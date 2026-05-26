"""시군구 hex 배치 자동 미세 조정 (hill climbing).

전략:
1. 현재 sigungu_hex.json 로드 → 시작 점수
2. 매 iter: 두 시군구 cell swap 시도
   - 같은 시도 안 swap (연결성 유지 위해)
   - 또는 다른 시도 swap (cluster 형태 변경)
3. eval → 점수 ↑면 accept, ↓면 revert
4. simulated annealing 옵션 — temperature 따라 점수 ↓도 일부 accept (local minima 탈출)

사용:
  .venv/bin/python scripts/refine_hex.py [--iters N] [--anneal]
"""
from __future__ import annotations
import argparse
import json
import random
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_sigungu_hex import evaluate, _load_geo

ROOT = Path(__file__).resolve().parent.parent
HEX = ROOT / "data" / "geo" / "sigungu_hex.json"
ADJ = ROOT / "data" / "geo" / "sigungu_adjacency.json"


def swap(hex_data, i, j):
    a = hex_data[i]
    b = hex_data[j]
    a["c"], b["c"] = b["c"], a["c"]
    a["r"], b["r"] = b["r"], a["r"]


def find_violators(hex_data):
    """ordering 위반 페어 (인접 시군구 쌍 중 동/서/북/남 순서 안 맞는)."""
    _, adj_data, centroid_by_code = _load_geo()
    by_code = {h["code"]: h for h in hex_data}
    code_to_idx = {h["code"]: i for i, h in enumerate(hex_data)}
    violators = []
    for p in adj_data["pairs"]:
        a, b = p["a"], p["b"]
        ca = centroid_by_code.get(a); cb = centroid_by_code.get(b)
        ha = by_code.get(a); hb = by_code.get(b)
        if not (ca and cb and ha and hb):
            continue
        g_east = ca[0] > cb[0]
        h_east = ha["c"] > hb["c"]
        g_north = ca[1] > cb[1]
        h_north = ha["r"] < hb["r"]
        # 둘 중 하나라도 어긋나면 violator
        if g_east != h_east or g_north != h_north:
            violators.append((code_to_idx[a], code_to_idx[b]))
    return violators


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--anneal", action="store_true")
    ap.add_argument("--targeted", action="store_true",
                    help="Hard test fail 케이스 우선 swap")
    ap.add_argument("--same-sido-prob", type=float, default=0.7,
                    help="같은 시도 안 swap 확률 (vs 다른 시도)")
    args = ap.parse_args()

    hex_data = json.loads(HEX.read_text())
    print(f"시작: {len(hex_data)} 시군구")
    scores = evaluate(hex_data)
    best = scores["total"]
    print(f"시작 점수: {best}/120  (hole {scores['n_holes']}, hard {scores['hard_pass']}/{scores['hard_total']})")

    # 시도별 시군구 인덱스
    sido_indices = {}
    for i, h in enumerate(hex_data):
        sido_indices.setdefault(h["sido"], []).append(i)

    accepted = 0
    rejected = 0
    t0 = time.time()
    for it in range(args.iters):
        # swap 후보 — targeted이면 violator pair, 아니면 random
        if args.targeted:
            violators = find_violators(hex_data)
            if violators:
                i, j = random.choice(violators)
            else:
                # 모든 violator 해결됐으면 random
                i, j = random.sample(range(len(hex_data)), 2)
        elif random.random() < args.same_sido_prob:
            valid_sidos = [s for s, idxs in sido_indices.items() if len(idxs) >= 2]
            if not valid_sidos:
                continue
            sido = random.choice(valid_sidos)
            i, j = random.sample(sido_indices[sido], 2)
        else:
            i, j = random.sample(range(len(hex_data)), 2)

        swap(hex_data, i, j)
        new_scores = evaluate(hex_data)
        new_total = new_scores["total"]
        # 연결성 깨지면 무조건 revert
        if new_scores["conn"] < scores["conn"]:
            swap(hex_data, i, j)
            rejected += 1
            continue

        accept = False
        if new_total > best:
            accept = True
        elif args.anneal:
            # simulated annealing
            T = max(0.1, 5 * (1 - it / args.iters))
            delta = new_total - best
            import math
            if random.random() < math.exp(delta / T):
                accept = True

        if accept:
            best = new_total
            scores = new_scores
            accepted += 1
            if accepted % 5 == 0 or new_total > scores.get("_print_thresh", 0):
                print(f"  iter {it+1:4d} accept → {new_total}/120 "
                      f"(hole {new_scores['n_holes']}, hard {new_scores['hard_pass']}/{new_scores['hard_total']})")
        else:
            swap(hex_data, i, j)  # revert
            rejected += 1

    dt = time.time() - t0
    print(f"\n총 {accepted} accept, {rejected} reject  ({dt:.1f}s)")
    final = evaluate(hex_data, verbose=True)

    # 저장
    HEX.write_text(json.dumps(hex_data, ensure_ascii=False), encoding="utf-8")
    print(f"→ {HEX.relative_to(ROOT)} 저장")


if __name__ == "__main__":
    main()
