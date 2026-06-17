// 뷰 간 공유 포커스 — 방식 전환 시 "보던 지역·배율"을 지역 앵커로 넘긴다.
//   각 뷰는 handle.report()→{region,scale} / handle.focusOn(region,scale) 두 개만 구현.
//   전환 직전 떠나는 뷰에서 capture → 새 뷰 렌더 후 apply.
//   scale ≤ 1.05면 "확대 안 한" 상태로 보고 region=null·scale=1 (전국) — 의미 없는 포커스 방지.
(function () {
  const NEAR_FULL = 1.05;
  window.Focus = {
    state: { unit: 'sido', region: null, scale: 1 },
    capture(handle) {
      if (!handle || typeof handle.report !== 'function') return;
      const r = handle.report() || {};
      const scale = r.scale || 1;
      const zoomed = scale > NEAR_FULL;
      this.state = {
        unit: this.state.unit,
        region: zoomed ? (r.region || null) : null,
        scale: zoomed ? scale : 1,
      };
    },
    apply(handle) {
      if (!handle || typeof handle.focusOn !== 'function') return;
      // 전국(기본)이면 새 뷰를 굳이 건드리지 않음 — 각자 기본 렌더 유지.
      if (this.state.region == null && (this.state.scale || 1) <= NEAR_FULL) return;
      handle.focusOn(this.state.region, this.state.scale);
    },
    // 단위(시도↔시군구)가 바뀌면 지역 앵커 무효 — Phase 3에서 부모/자식 변환.
    setUnit(u) { if (u && u !== this.state.unit) this.state = { unit: u, region: null, scale: 1 }; },
  };
})();
