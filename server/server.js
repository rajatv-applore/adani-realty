/*
 * Adani villa, static site + Blender photoreal render service.
 * Pure Node built-ins (no npm deps). Serves the built interactive Babylon app
 * from dist/ and adds a render-job API that drives Blender head-less via
 * blender/villa_render.py.
 *
 *   GET  /                      -> dist/index.html  (run `npm run build` first)
 *   GET  /api/render           -> { blenderAvailable, blenderPath, busy, queued }
 *   POST /api/render           -> { jobId }  (body: {view,engine,time,villaNo,samples,res,zones})
 *   GET  /api/render/:jobId    -> { status, message, progress, image?, error? }
 *   GET  /renders/<file>.png   -> rendered image
 *
 * Config via env:
 *   PORT          (default 8770)
 *   BLENDER_PATH  explicit path to the Blender binary (else auto-detected)
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const { spawn } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const PUBLIC_DIR = path.join(ROOT, 'dist');
const RENDER_DIR = path.join(ROOT, 'renders');
const SCRIPT = path.join(ROOT, 'blender', 'villa_render.py');
const PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : 8770;
if (!fs.existsSync(RENDER_DIR)) fs.mkdirSync(RENDER_DIR, { recursive: true });

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.webp': 'image/webp', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };

/* ---------- locate Blender ---------- */
function detectBlender() {
  if (process.env.BLENDER_PATH && fs.existsSync(process.env.BLENDER_PATH)) return process.env.BLENDER_PATH;
  // Checked in order, first match wins: macOS app installs (Homebrew cask / DMG), then Linux.
  const candidates = [
    '/Applications/Blender.app/Contents/MacOS/Blender',
    path.join(os.homedir(), 'Applications', 'Blender.app', 'Contents', 'MacOS', 'Blender'),
    '/opt/homebrew/bin/blender',
    '/usr/local/bin/blender',
    '/snap/bin/blender',
    '/usr/bin/blender',
  ];
  return candidates.find((p) => fs.existsSync(p)) || null;
}
let BLENDER = detectBlender();

/* ---------- job store + single-worker queue ---------- */
const jobs = new Map();           // jobId -> job
const queue = [];
let running = false;

function startNext() {
  if (running || queue.length === 0) return;
  BLENDER = BLENDER || detectBlender();
  if (!BLENDER) { // flush queue with error
    while (queue.length) {
      const id = queue.shift(); const j = jobs.get(id);
      j.status = 'error'; j.error = 'Blender is not installed. Install it with `brew install --cask blender` or set BLENDER_PATH. See README.md.';
    }
    return;
  }
  running = true;
  const id = queue.shift();
  const job = jobs.get(id);
  job.status = 'rendering';
  job.message = 'Launching Blender…';

  const out = path.join(RENDER_DIR, id + '.png');
  const dataFile = path.join(RENDER_DIR, id + '.json');
  try { fs.writeFileSync(dataFile, JSON.stringify({ zones: job.params.zones || {} })); } catch (_) {}

  const args = ['-b', '-P', SCRIPT, '--',
    '--out', out, '--engine', job.params.engine, '--samples', String(job.params.samples),
    '--res', job.params.res, '--view', job.params.view, '--time', job.params.time,
    '--villa-no', job.params.villaNo, '--data', dataFile];
  if (job.params.forceCpu) args.push('--force-cpu');

  job.startedAt = Date.now();
  const child = spawn(BLENDER, args, { cwd: ROOT });
  let tail = '';
  const onData = (buf) => {
    const s = buf.toString();
    tail = (tail + s).slice(-4000);
    const m = s.match(/Sample\s+(\d+)\/(\d+)/g);
    if (m && m.length) {
      const last = m[m.length - 1].match(/Sample\s+(\d+)\/(\d+)/);
      if (last) { job.progress = Math.round((+last[1] / +last[2]) * 100); job.message = 'Rendering ' + job.progress + '%'; }
    } else if (/Synchronizing|Building|Updating|Loading/i.test(s)) {
      job.message = 'Preparing scene…';
    }
  };
  child.stdout.on('data', onData);
  child.stderr.on('data', onData);
  child.on('error', (err) => {
    job.status = 'error'; job.error = 'Failed to launch Blender: ' + err.message;
    running = false; startNext();
  });
  child.on('close', (code) => {
    if (code === 0 && fs.existsSync(out)) {
      job.status = 'done'; job.progress = 100; job.message = 'Complete';
      job.image = '/renders/' + id + '.png';
      job.ms = Date.now() - job.startedAt;
    } else {
      job.status = 'error';
      job.error = 'Blender exited with code ' + code + '. ' + (tail.split('\n').filter(Boolean).slice(-3).join(' | ') || '');
    }
    running = false;
    startNext();
  });
}

/* ---------- http ---------- */
function sendJSON(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  res.end(body);
}
function serveFile(res, fp) {
  fs.readFile(fp, (e, data) => {
    if (e) { res.writeHead(404); return res.end('not found'); }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(fp)] || 'application/octet-stream',
      'Cache-Control': 'no-store, no-cache, must-revalidate' });
    res.end(data);
  });
}

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://localhost');
  let p = decodeURIComponent(u.pathname);

  // ---- render capability ----
  if (p === '/api/render' && req.method === 'GET') {
    return sendJSON(res, 200, { blenderAvailable: !!BLENDER, blenderPath: BLENDER || null,
      busy: running, queued: queue.length });
  }
  // ---- start a render ----
  if (p === '/api/render' && req.method === 'POST') {
    let body = '';
    req.on('data', c => { body += c; if (body.length > 1e6) req.destroy(); });
    req.on('end', () => {
      let b = {}; try { b = JSON.parse(body || '{}'); } catch (_) {}
      const id = crypto.randomBytes(6).toString('hex');
      const params = {
        view: ['hero', 'front', 'aerial', 'pool'].includes(b.view) ? b.view : 'hero',
        engine: b.engine === 'EEVEE' ? 'EEVEE' : 'CYCLES',
        time: b.time === 'dusk' ? 'dusk' : 'day',
        villaNo: /^\d{1,3}$/.test(String(b.villaNo || '')) ? String(b.villaNo).padStart(2, '0') : '08',
        samples: Math.min(512, Math.max(16, parseInt(b.samples, 10) || 96)),
        res: /^\d{3,4}x\d{3,4}$/.test(b.res || '') ? b.res : '1600x1000',
        zones: (b.zones && typeof b.zones === 'object') ? b.zones : {},
        forceCpu: !!b.forceCpu,
      };
      jobs.set(id, { id, status: 'queued', message: 'Queued', progress: 0, params, createdAt: Date.now() });
      queue.push(id);
      startNext();
      return sendJSON(res, 202, { jobId: id, blenderAvailable: !!BLENDER });
    });
    return;
  }
  // ---- job status ----
  if (p.startsWith('/api/render/') && req.method === 'GET') {
    const id = p.split('/').pop();
    const j = jobs.get(id);
    if (!j) return sendJSON(res, 404, { error: 'unknown job' });
    return sendJSON(res, 200, { jobId: j.id, status: j.status, message: j.message,
      progress: j.progress, image: j.image || null, error: j.error || null, ms: j.ms || null });
  }
  // ---- rendered images ----
  if (p.startsWith('/renders/')) {
    const fp = path.join(RENDER_DIR, path.basename(p));
    if (!fp.startsWith(RENDER_DIR)) { res.writeHead(403); return res.end('no'); }
    return serveFile(res, fp);
  }

  // ---- static site ----
  if (p === '/') p = '/index.html';
  const fp = path.join(PUBLIC_DIR, p);
  if (!fp.startsWith(PUBLIC_DIR + path.sep)) { res.writeHead(403); return res.end('no'); }
  serveFile(res, fp);
});

server.listen(PORT, () => {
  if (!fs.existsSync(path.join(PUBLIC_DIR, 'index.html'))) {
    console.warn('dist/index.html not found, run `npm run build` first.');
  }
  console.log('serving ' + PUBLIC_DIR + ' on http://localhost:' + PORT);
  console.log('Blender: ' + (BLENDER || 'NOT FOUND (set BLENDER_PATH or install Blender)'));
});
