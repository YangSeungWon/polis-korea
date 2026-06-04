"""시군구 hex 알고리즘 variant 비교.

여러 ENV 옵션 조합으로 build_sigungu_hex 호출 + eval. 점수 표 출력.

옵션:
  ANCHOR_MODE: manual | centroid | centroid-mainland
  CELL_SIZE:   0.15 / 0.18 / 0.20
  ...
"""
from __future__ import annotations
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "scripts" / "build_sigungu_hex.py"
EVAL = ROOT / "scripts" / "eval_sigungu_hex.py"
PY = str(ROOT / ".venv" / "bin" / "python")

VARIANTS = [
    {"ANCHOR_MODE": "manual",            "CELL_SIZE": "0.18"},
    {"ANCHOR_MODE": "centroid",          "CELL_SIZE": "0.18"},
    {"ANCHOR_MODE": "centroid-mainland", "CELL_SIZE": "0.18"},
    {"ANCHOR_MODE": "manual",            "CELL_SIZE": "0.15"},
    {"ANCHOR_MODE": "manual",            "CELL_SIZE": "0.20"},
    {"ANCHOR_MODE": "centroid-mainland", "CELL_SIZE": "0.15"},
    {"ANCHOR_MODE": "centroid-mainland", "CELL_SIZE": "0.20"},
]


def run(env_overrides):
    env = os.environ.copy()
    env.update(env_overrides)
    subprocess.run([PY, str(BUILD)], env=env, capture_output=True, check=True)
    eval_out = subprocess.run([PY, str(EVAL)], env=env, capture_output=True, text=True, check=True)
    txt = eval_out.stdout
    return parse_scores(txt)


def parse_scores(txt):
    """eval stdout에서 각 점수 항목 추출."""
    out = {}
    patterns = {
        "conn": r"점수: (\d+)/30",
        "sido_adj": r"F1 \d+\.\d+%\s*→ (\d+)/15",
        "sido_topo": r"시도 위상.*?→ (\d+)/10",
        "sg_adj": r"시군구 polygon 인접.*?F1 \d+\.\d+%\s*→ (\d+)/25",
        "sg_topo": r"시군구 위상.*?→ (\d+)/10",
        "hole": r"hole \d+\s*→ (\d+)/10",
        "order": r"ordering 맞음.*?\(\d+\.\d+%\)\s*→ (\d+)/10",
        "hard": r"Hard tests[\s\S]*?(\d+)/10\n\n== 종합",
        "total": r"= (\d+)/120",
    }
    for k, p in patterns.items():
        m = re.search(p, txt, re.DOTALL)
        out[k] = int(m.group(1)) if m else 0
    return out


def main():
    print(f"{'#':>2} {'ANCHOR':18s} {'CELL':5s} {'conn':5s} {'sido_adj':9s} {'sido_topo':10s} "
          f"{'sg_adj':7s} {'sg_topo':8s} {'hole':5s} {'order':6s} {'hard':5s}  {'TOTAL':>5s}")
    print("-" * 110)
    results = []
    for i, v in enumerate(VARIANTS):
        try:
            scores = run(v)
        except subprocess.CalledProcessError as e:
            print(f"{i+1:>2} {v.get('ANCHOR_MODE','?'):18s} {v.get('CELL_SIZE','?'):5s} ERR {e}")
            continue
        results.append((v, scores))
        print(f"{i+1:>2} {v.get('ANCHOR_MODE',''):18s} {v.get('CELL_SIZE',''):5s} "
              f"{scores['conn']:>5d} {scores['sido_adj']:>9d} {scores['sido_topo']:>10d} "
              f"{scores['sg_adj']:>7d} {scores['sg_topo']:>8d} "
              f"{scores['hole']:>5d} {scores['order']:>6d} {scores['hard']:>5d}  "
              f"{scores['total']:>5d}")

    # best
    if results:
        best_v, best_s = max(results, key=lambda x: x[1]["total"])
        print(f"\n🏆 BEST: {best_v} → {best_s['total']}/120")
        # 그 config로 다시 build 저장
        env = os.environ.copy(); env.update(best_v)
        subprocess.run([PY, str(BUILD)], env=env, capture_output=True, check=True)
        print(f"  → data/geo/sigungu_hex.json 저장 (best variant)")


if __name__ == "__main__":
    main()
