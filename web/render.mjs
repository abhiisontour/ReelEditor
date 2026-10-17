// reelkit frame renderer. Serves the filesystem over a local HTTP server (file:// fetch is blocked),
// loads a page that defines window.renderFrame(n) and sets window.ready, screenshots transparent PNGs.
// usage: node render.mjs <abs page path + ?query> <outdir> <frames|list "1,5,9"> [pages=2]
import { chromium } from 'playwright-core';
import fs from 'fs'; import path from 'path'; import http from 'http';
const MIME = { '.html':'text/html', '.json':'application/json', '.js':'text/javascript', '.css':'text/css', '.woff2':'font/woff2', '.woff':'font/woff', '.png':'image/png', '.jpg':'image/jpeg', '.svg':'image/svg+xml' };
const srv = http.createServer((q, r) => { const f = decodeURIComponent(q.url.split('?')[0]);
  fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); return r.end(); } r.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(d); }); });
await new Promise(ok => srv.listen(0, '127.0.0.1', ok)); const PORT = srv.address().port;
const [,, page, out, frames, nPages = 2] = process.argv;
fs.mkdirSync(out, { recursive: true });
const exe = process.env.REELKIT_CHROME || fs.readdirSync('/opt/pw-browsers').filter(d => d.startsWith('chromium_headless_shell')).map(d => `/opt/pw-browsers/${d}/chrome-linux/headless_shell`)[0];
const browser = await chromium.launch({ executablePath: exe, args: ['--font-render-hinting=none'] });
const list = String(frames).includes(',') ? frames.split(',').map(Number) : [...Array(+frames).keys()];
const chunks = Array.from({ length: +nPages }, (_, i) => list.filter((_, j) => j % +nPages === i));
let done = 0; const t0 = Date.now();
await Promise.all(chunks.map(async ch => {
  const p = await browser.newPage({ viewport: { width: +(process.env.VW||1080), height: +(process.env.VH||1920) }, deviceScaleFactor: 1 });
  p.on('pageerror', e => console.error('PAGE ERROR', e.message));
  await p.goto(`http://127.0.0.1:${PORT}${page.startsWith('/') ? '' : '/'}${page}`);
  await p.waitForFunction(() => window.ready === true, null, { timeout: 60000 });
  for (const n of ch) {
    await p.evaluate(n => window.renderFrame(n), n);
    await p.screenshot({ path: `${out}/${String(n).padStart(5, '0')}.png`, omitBackground: true });
    if (++done % 100 === 0) console.log(`${done}/${list.length} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
}));
await browser.close(); srv.close();
