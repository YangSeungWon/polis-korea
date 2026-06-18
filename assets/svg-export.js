// 지도 SVG → PNG 즉석 저장. 보는 뷰(직위·표현 토글한 그 상태)를 그대로 내려받는다.
// 정적 사전생성(직위×표현 수백 장) 대신 클라이언트에서 현재 SVG를 직렬화→캔버스→PNG.
//   - 모든 변종 커버, 저장 0, 항상 최신.
//   - 지도 SVG 클래스에 '이미지 저장' 버튼을 붙임(토글로 SVG 교체돼도 래퍼 1버튼이 현재 SVG 저장).
(function () {
  'use strict';

  function svgToPng(svg, opts) {
    opts = opts || {};
    const scale = opts.scale || 2, pad = opts.pad == null ? 18 : opts.pad, bg = opts.bg || '#ffffff';
    const clone = svg.cloneNode(true);
    let w, h;
    const vb = svg.getAttribute('viewBox');
    if (vb) { const p = vb.split(/[ ,]+/).map(Number); w = p[2]; h = p[3]; }
    else { const r = svg.getBoundingClientRect(); w = r.width; h = r.height; }
    clone.setAttribute('width', w); clone.setAttribute('height', h);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    // 페이지 폰트 패밀리를 SVG 루트에 박아 캔버스 렌더 시 폰트 폴백 일관화
    clone.style.fontFamily = getComputedStyle(document.body).fontFamily;
    const xml = new XMLSerializer().serializeToString(clone);
    const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
    const img = new Image();
    img.onload = function () {
      const W = Math.round((w + pad * 2) * scale), H = Math.round((h + pad * 2) * scale);
      const c = document.createElement('canvas'); c.width = W; c.height = H;
      const ctx = c.getContext('2d');
      if (bg) { ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H); }
      ctx.drawImage(img, pad * scale, pad * scale, w * scale, h * scale);
      c.toBlob(function (blob) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = (opts.filename || 'polis-map') + '.png';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
      }, 'image/png');
    };
    img.onerror = function () { alert('이미지 저장에 실패했습니다.'); };
    img.src = url;
  }
  window.svgToPng = svgToPng;

  const MAP_SEL = [
    'svg.governor-hex-svg', 'svg.council-hex-svg', 'svg.ar-sidocluster-svg',
    'svg.sido-map-svg', 'svg.sigungu-map-svg', 'svg.district-hex-svg', 'svg.district-map-svg',
    'svg.parliament-chart', 'svg.hex-pane',
  ].join(',');

  // 지도 종류 → [클래스, 공유키(build_share_pages와 일치), 파일명 꼬리표]. 더 구체적인 클래스를 먼저 —
  // council-hex-svg는 result-map(대선 시군구 단색)·cartogram-map(시군구 비례)과 공존하므로 그 뒤에 둬야 오분류 안 됨.
  const VIEW_DEFS = [
    ['turnout-map', 'turnout', '투표율'],
    ['result-map', 'result', '시군구결과'],
    ['cartogram-map', 'sgg-prop', '시군구비례'],
    ['sigungu-map-svg', 'sgg-geo', '시군구지도'],
    ['sido-winner-hex', 'sido1', '시도1위'],        // governor-hex-svg와 공존 → 먼저
    ['district-hex-svg', 'district', '선거구1위'],
    ['district-map-svg', 'district-geo', '선거구지도'],
    ['governor-hex-svg', 'governor', '광역단체장'],
    ['ar-sidocluster-svg', 'dorling', 'dorling'],
    ['sido-map-svg', 'geo', '지도'],
    ['parliament-chart', 'seats', '의석'],
    ['council-hex-svg', 'council', '의원'],
    ['hex-pane', '', 'hex'],   // 폴 hex — 저장만(아카이브 아님 → 공유키 없음)
  ];
  function classify(svg) {
    for (let i = 0; i < VIEW_DEFS.length; i++) if (svg.classList.contains(VIEW_DEFS[i][0])) return VIEW_DEFS[i];
    return null;
  }
  function viewLabel(svg) { const d = classify(svg); return d ? d[2] : ''; }
  function shareKey(svg) { const d = classify(svg); return d ? d[1] : ''; }
  // archive 페이지 slug (/archive/{slug}/). 공유페이지는 결과 아카이브 뷰에만 존재.
  function archiveSlug() {
    const m = location.pathname.match(/\/archive\/([^/]+)\//);
    return m ? m[1] : '';
  }
  function fnameBase() {
    // document.title 'polis · …'의 앞 브랜드를 풀 도메인 'polis-ysw-kr'로 (파일명에 사이트 표시).
    return (document.title || 'polis-map')
      .replace(/^polis(?=\s|·|$)/, 'polis-ysw-kr')
      .replace(/\s*·\s*/g, '-')
      .replace(/[^0-9a-zA-Z가-힣_-]+/g, '_').replace(/_+/g, '_').replace(/^[-_]+|[-_]+$/g, '').slice(0, 60);
  }

  function mkBtn(text, title, onClick) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'svg-save-btn'; b.textContent = text; b.title = title;
    b.addEventListener('click', onClick);
    return b;
  }

  function attach(svg) {
    const wrap = svg.parentElement;
    if (!wrap || wrap.dataset.svgSave) return;
    wrap.dataset.svgSave = '1';
    if (getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';
    const bar = document.createElement('div');
    bar.className = 'svg-save-bar';
    // 이미지 저장 — 보는 뷰 그대로 PNG
    bar.appendChild(mkBtn('↓ 이미지', '이 지도를 PNG로 저장', function () {
      const cur = wrap.querySelector('svg'); if (!cur) return;
      const v = viewLabel(cur);
      svgToPng(cur, { filename: fnameBase() + (v ? '_' + v : '') });
    }));
    // 공유 — 그 뷰 미리보기가 뜨는 링크 복사(archive 결과뷰만)
    const slug = archiveSlug();
    if (slug) {
      bar.appendChild(mkBtn('↗ 공유', '이 뷰 미리보기 링크 복사', function (e) {
        const cur = wrap.querySelector('svg'); if (!cur) return;
        const k = shareKey(cur); if (!k) return;
        const url = location.origin + '/share/' + slug + '/' + k + '/';
        const done = function () {
          const btn = e.currentTarget; const old = btn.textContent;
          btn.textContent = '✓ 복사됨'; setTimeout(function () { btn.textContent = old; }, 1400);
        };
        if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, done);
        else { prompt('공유 링크', url); }
      }));
    }
    wrap.appendChild(bar);
  }

  function scan() { document.querySelectorAll(MAP_SEL).forEach(attach); }

  // 공유 링크 딥링크 — /archive/{slug}/#geo 로 들어오면 그 뷰 토글을 활성화하고 스크롤.
  // 미리보기(og:image)와 착지 뷰를 일치시킨다. 뷰 키→SVG 클래스로 섹션 역추적(키 중복 회피).
  const KEY2CLASS = {
    governor: 'governor-hex-svg', council: 'council-hex-svg', dorling: 'ar-sidocluster-svg',
    geo: 'sido-map-svg', seats: 'parliament-chart', turnout: 'turnout-map',
    result: 'result-map', 'sgg-prop': 'cartogram-map', 'sgg-geo': 'sigungu-map-svg',
    sido1: 'sido-winner-hex', district: 'district-hex-svg', 'district-geo': 'district-map-svg',
  };
  function applyHashView() {
    const key = (location.hash || '').replace(/^#/, '').replace(/^view=/, '');
    const cls = KEY2CLASS[key];
    if (!cls) return false;
    const svg = document.querySelector('.ar-sido-view svg.' + cls) || document.querySelector('svg.' + cls);
    if (!svg) return false;
    const view = svg.closest('.ar-sido-view');
    if (view) {
      const host = view.parentElement;
      const tab = host && host.querySelector('.ar-sido-toggle .seg-btn[data-enc="' + view.dataset.view + '"]');
      if (tab && !tab.classList.contains('is-active')) tab.click();
      (view.closest('.ar-section') || view).scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      svg.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return true;
  }

  const obs = new MutationObserver(scan);
  if (document.body) obs.observe(document.body, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', function () {
    setTimeout(scan, 1500);
    // 지도는 비동기 렌더 — 뜰 때까지 몇 번 재시도
    if (location.hash) [1600, 2600, 3600].forEach(function (t) { setTimeout(applyHashView, t); });
  });
  window.addEventListener('hashchange', applyHashView);
})();
