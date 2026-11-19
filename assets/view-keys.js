// 생성물 — scripts/build/view_registry.py가 data/view_registry.json에서 만든다. 손수정 X.
// 뷰 키 = {host} 또는 {host}-{mode}. parseKey는 긴 host 토큰을 먼저 맞춘다(parse_key와 같은 규칙).
(function () {
  const R = {"enc2mode": {"dorling": "dorling", "geo": "geo", "grid": "grid", "hex": "hex", "map": "geo", "polls": "polls", "result": "result", "turnout": "turnout", "turnout-map": "turnout-geo", "격자": "grid", "단색": "flat"}, "hosts": ["gov", "metro", "metro-prop", "council", "sggturn", "sgg", "sggprop", "sido", "seats", "sidoseat", "prop", "district", "electors", "pollgov", "pollmayor", "pollsido", "polldistrict", "tkapproval", "tkparty", "tkcand", "tkglead", "lineage", "status", "dashgov", "dashmayor", "byemap"], "modes": ["hex", "geo", "grid", "dorling", "turnout", "turnout-geo", "flat", "polls", "result"]};
  const MODES = new Set(R.modes);
  const HOSTS = R.hosts.slice().sort((a, b) => b.length - a.length);
  function modeOf(enc) { return R.enc2mode[String(enc == null ? '' : enc).trim()] || null; }
  function keyFor(host, mode) { return mode ? host + '-' + mode : host; }
  function parseKey(key) {
    if (R.hosts.indexOf(key) >= 0) return [key, null];
    for (const t of HOSTS) {
      if (key.indexOf(t + '-') === 0) { const m = key.slice(t.length + 1); return MODES.has(m) ? [t, m] : null; }
    }
    return null;
  }
  window.ViewKeys = { modeOf, keyFor, parseKey };
})();
