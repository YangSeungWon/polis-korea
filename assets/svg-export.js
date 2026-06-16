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
    'svg.sido-map-svg', 'svg.parliament-chart', 'svg.hex-pane',
  ].join(',');

  // 지도 종류 → 파일명 꼬리표(같은 페이지 여러 지도 구분)
  const VIEW = {
    'governor-hex-svg': '광역단체장', 'council-hex-svg': '의원', 'ar-sidocluster-svg': 'dorling',
    'sido-map-svg': '지도', 'parliament-chart': '의석', 'hex-pane': 'hex',
  };
  function viewLabel(svg) {
    for (const cls of svg.classList) if (VIEW[cls]) return VIEW[cls];
    return '';
  }
  function fnameBase() {
    // document.title이 이미 'polis · …'라 그대로 정제(중복 prefix 방지)
    return (document.title || 'polis-map')
      .replace(/[·]/g, '-').replace(/[^0-9a-zA-Z가-힣_-]+/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '').slice(0, 60);
  }

  function attach(svg) {
    const wrap = svg.parentElement;
    if (!wrap || wrap.dataset.svgSave) return;
    wrap.dataset.svgSave = '1';
    if (getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'svg-save-btn';
    btn.textContent = '↓ 이미지';
    btn.title = '이 지도를 PNG로 저장';
    btn.addEventListener('click', function () {
      const cur = wrap.querySelector('svg');
      if (!cur) return;
      const v = viewLabel(cur);
      svgToPng(cur, { filename: fnameBase() + (v ? '_' + v : '') });
    });
    wrap.appendChild(btn);
  }

  function scan() { document.querySelectorAll(MAP_SEL).forEach(attach); }

  const obs = new MutationObserver(scan);
  if (document.body) obs.observe(document.body, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', function () { setTimeout(scan, 1500); });
})();
