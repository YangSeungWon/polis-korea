// 시도 비례 뷰 (대선 전용) — 공유 Archive.sidoCluster(mode:'proportional')로 위임.
//   격자(drawGrid)=drawHex / dorling(drawDorling). render-sido-view(tc=1)·폴 페이지가
//   Archive.sidoProp.drawGrid/drawDorling 호출. 입력 = races[{sido, candidates[votes|share,pct], valid_votes|weight}].
//   1 hex ≈ 10만표(allocate가 득표 비율 배분, 승자독식 단색 거부). seedGap·smallR은 sidoCluster가 mode별 관리.
(function () {
  function drawGrid(host, races, opts) {
    opts = opts || {};
    return window.Archive.sidoCluster.drawHex(host, races, { mode: 'proportional', legend: opts.legend, onSelect: opts.onSelect, missOf: opts.missOf });
  }
  function drawDorling(host, races, opts) {
    opts = opts || {};
    return window.Archive.sidoCluster.drawDorling(host, races, { mode: 'proportional', legend: opts.legend, onSelect: opts.onSelect, missOf: opts.missOf });
  }
  window.Archive = window.Archive || {};
  window.Archive.sidoProp = { drawGrid, drawDorling };
})();
