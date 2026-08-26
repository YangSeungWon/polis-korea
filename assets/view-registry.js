// 지도 뷰 표 — 생성 파일. 편집 금지.
// 정본: data/view_registry.json · 생성: scripts/build/sync_view_registry_js.py
(function () {
  'use strict';

// === VIEW_REGISTRY auto-generated ===
// data/view_registry.json에서 sync. 손으로 수정하지 말 것 —
// scripts/build/sync_view_registry_js.py 재실행으로 갱신.
// ⚠️ 배열 순서가 load-bearing: 분류는 첫 substring 매칭이 이긴다.
//    한 SVG가 여러 클래스를 함께 갖는다(시군구 결과 = council-hex-svg result-map).
//    근거는 JSON 각 항목의 note에 있다.
const VIEW_REGISTRY = [
  { key: 'sgg-turnout', classes: ['sgg-turnout'], label: '시군구 투표율', fname: '시군구투표율' },
  { key: 'sgg-turnout-geo', classes: ['sigungu-turnout-geo'], label: '시군구 투표율 지도', fname: '시군구투표율지도' },
  { key: 'turnout-geo', classes: ['sido-turnout-geo'], label: '투표율 지도', fname: '투표율지도' },
  { key: 'district-turnout-geo', classes: ['district-turnout-geo'], label: '선거구 투표율 지도', fname: '선거구투표율지도' },
  { key: 'district-turnout', classes: ['district-turnout'], label: '선거구 투표율', fname: '선거구투표율' },
  { key: 'turnout', classes: ['turnout-map'], label: '투표율', fname: '투표율' },
  { key: 'result', classes: ['result-map'], label: '시군구 결과', fname: '시군구결과' },
  { key: 'sgg-prop', classes: ['cartogram-map'], label: '시군구 비례', fname: '시군구비례' },
  { key: 'sgg-geo', classes: ['sigungu-map'], label: '시군구 지도', fname: '시군구지도' },
  { key: 'sido1', classes: ['sido-winner-hex'], label: '시도 1위', fname: '시도1위' },
  { key: 'district', classes: ['district-hex'], label: '선거구 1위', fname: '선거구1위' },
  { key: 'district-geo', classes: ['district-map'], label: '선거구 지도', fname: '선거구지도' },
  { key: 'governor', classes: ['governor-hex'], label: '광역단체장', fname: '광역단체장' },
  { key: 'council', classes: ['council-hex'], label: '광역의원', fname: '의원' },
  { key: 'dorling', classes: ['ar-sidocluster'], label: '의석 비례', fname: 'dorling' },
  { key: 'geo', classes: ['sido-map'], label: '지리 지도', fname: '지도' },
  { key: 'seats', classes: ['parliament-chart'], label: '의석수', fname: '의석' },
  { key: '', classes: ['hex-pane'], label: 'hex', fname: 'hex' },
];
// SVG class 문자열 → 뷰 키. archive 뷰가 아니면(빈 키) '' 를 준다.
function viewKeyOf(cls) {
  const s = cls || '';
  for (const v of VIEW_REGISTRY) if (v.classes.some(c => s.includes(c))) return v.key;
  return null;
}
function viewMetaOf(key) {
  return VIEW_REGISTRY.find(v => v.key === key) || null;
}
window.VIEW_REGISTRY = VIEW_REGISTRY;
window.viewKeyOf = viewKeyOf;
window.viewMetaOf = viewMetaOf;
// === /VIEW_REGISTRY ===
})();
