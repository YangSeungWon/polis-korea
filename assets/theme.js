// 테마 토글 — system (OS prefers) ↔ light ↔ dark 순환, localStorage 저장.
// 모든 페이지에서 <button id="theme-toggle"> 있으면 자동 binding.
(function () {
  const KEY = 'vote-ysw-theme';
  const MODES = ['system', 'light', 'dark'];
  const LABEL = { system: '자동', light: '라이트', dark: '다크' };
  // 미니 SVG (currentColor) — 14px, 1.5px stroke
  const SVG = {
    system: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="2" y="3" width="12" height="9" rx="1"/><path d="M5 14h6M8 12v2"/></svg>',
    light:  '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="8" cy="8" r="3"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4"/></svg>',
    dark:   '<svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M11.5 1.5a6 6 0 1 0 3 11.4A5 5 0 0 1 11.5 1.5z"/></svg>',
  };

  function getMode() {
    try { return localStorage.getItem(KEY) || 'system'; } catch (e) { return 'system'; }
  }
  function setMode(m) {
    try { localStorage.setItem(KEY, m); } catch (e) {}
    applyMode(m);
    refreshBtn();
  }
  function applyMode(m) {
    const root = document.documentElement;
    if (m === 'light') root.setAttribute('data-theme', 'light');
    else if (m === 'dark') root.setAttribute('data-theme', 'dark');
    else root.removeAttribute('data-theme');
  }
  function nextMode(cur) {
    return MODES[(MODES.indexOf(cur) + 1) % MODES.length];
  }
  function refreshBtn() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    const m = getMode();
    btn.innerHTML = `<span class="ico">${SVG[m]}</span>${LABEL[m]}`;
    btn.setAttribute('aria-label', `테마: ${LABEL[m]} (클릭하여 변경)`);
  }
  function init() {
    applyMode(getMode());
    refreshBtn();
    const btn = document.getElementById('theme-toggle');
    if (btn && !btn.dataset.bound) {
      btn.dataset.bound = '1';
      btn.addEventListener('click', () => setMode(nextMode(getMode())));
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  // 즉시 attribute 적용 (FOUC 방지) — readyState=interactive 전에도
  applyMode(getMode());
})();
