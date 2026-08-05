// 정적 서버 — 배포본과 같은 조건(절대경로 /assets/…, <base href="/">)으로 띄운다.
// file:// 로 열면 base·fetch가 달라져 실제와 다른 걸 검사하게 된다.
import http from 'http';
import fs from 'fs';
import path from 'path';

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.geojson': 'application/json; charset=utf-8', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp',
  '.txt': 'text/plain; charset=utf-8', '.xml': 'application/xml; charset=utf-8',
  '.woff2': 'font/woff2',
};

export function serve(root, port = 8099) {
  const srv = http.createServer((req, res) => {
    let u = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
    if (u.includes('..')) { res.writeHead(400); return res.end(); }
    let f = path.join(root, u);
    try { if (fs.statSync(f).isDirectory()) f = path.join(f, 'index.html'); } catch { /* 404 아래 */ }
    try {
      const buf = fs.readFileSync(f);
      res.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream' });
      res.end(buf);
    } catch {
      res.writeHead(404, { 'content-type': 'text/plain' });
      res.end('404');
    }
  });
  // 포트가 물려 있으면 다음 포트로 — 잔여 프로세스나 CI 병렬 실행에 죽지 않게.
  return new Promise((resolve, reject) => {
    let p = port;
    const attempt = () => {
      srv.once('error', (e) => {
        if (e.code === 'EADDRINUSE' && p < port + 30) { p += 1; attempt(); }
        else reject(e);
      });
      srv.listen(p, '127.0.0.1', () => resolve({
        url: `http://127.0.0.1:${p}`,
        close: () => new Promise((x) => srv.close(x)),
      }));
    };
    attempt();
  });
}
