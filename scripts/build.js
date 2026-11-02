#!/usr/bin/env node
/**
 * Build: src/ -> dist/index.html
 *
 * Produces a single, self-contained, offline-capable HTML file by inlining:
 *   - every <link rel="stylesheet" href="css/*.css" />   -> one <style> block
 *   - every url('../fonts/*.woff2') inside that CSS        -> base64 data URI
 *   - <script src="vendor/*.js"></script>                  -> inline <script>
 *   - consecutive <script src="js/*.js"></script> tags     -> one inline <script>
 *     (app scripts are concatenated so they share one script scope, exactly
 *      as if they had been written in a single file)
 *   - js/villa-assets.js is generated, not read: src/assets/villa/scene.json
 *     (exported by `npm run export:web`) + its textures, sprites and sky HDRIs
 *     as data URIs, exposed as the VILLA_ASSETS constant
 *
 * Usage: node scripts/build.js   (or: npm run build)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'src');
const DIST = path.join(ROOT, 'dist');
const OUT = path.join(DIST, 'index.html');

const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');

const VILLA_DIR = path.join(SRC, 'assets', 'villa');
const MIME = { '.webp': 'image/webp', '.jpg': 'image/jpeg', '.png': 'image/png', '.hdr': 'application/octet-stream' };

function villaAssets() {
  const sceneFile = path.join(VILLA_DIR, 'scene.json');
  if (!fs.existsSync(sceneFile)) {
    throw new Error('src/assets/villa/scene.json missing, run `npm run export:web` first');
  }
  const files = {};
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((e) => {
    const fp = path.join(dir, e.name);
    if (e.isDirectory()) return walk(fp);
    const mime = MIME[path.extname(e.name)];
    if (!mime) return;
    const rel = path.relative(VILLA_DIR, fp).split(path.sep).join('/');
    files[rel] = 'data:' + mime + ';base64,' + fs.readFileSync(fp).toString('base64');
  });
  walk(VILLA_DIR);
  return 'const VILLA_ASSETS={scene:' + fs.readFileSync(sceneFile, 'utf8').trim() +
    ',files:' + JSON.stringify(files) + '};\n';
}

const readScript = (rel) => (rel === 'js/villa-assets.js' ? villaAssets() : read(rel));

function inlineFonts(css) {
  return css.replace(/url\('\.\.\/fonts\/([^']+\.woff2)'\)/g, (_, name) => {
    const b64 = fs.readFileSync(path.join(SRC, 'fonts', name)).toString('base64');
    return 'url(data:font/woff2;base64,' + b64 + ')';
  });
}

function build() {
  let html = read('index.html');

  // 1. stylesheets -> single <style>
  const cssRun = /(?:[ \t]*<link rel="stylesheet" href="(css\/[^"]+)" \/>\n)+/;
  const cssMatch = html.match(cssRun);
  if (!cssMatch) throw new Error('No stylesheet <link> tags found in src/index.html');
  const cssFiles = [...cssMatch[0].matchAll(/href="([^"]+)"/g)].map((m) => m[1]);
  const css = cssFiles.map((f) => inlineFonts(read(f))).join('');
  html = html.replace(cssRun, () => '<style>\n' + css + '</style>\n');

  // 2. vendor libraries -> inline, one <script> each
  html = html.replace(/<script src="vendor\/([^"]+)"><\/script>/g, (_, name) =>
    '<script>\n/* ' + name + ' (bundled) */\n' + read('vendor/' + name) + '\n</script>');

  // 3. application scripts -> one concatenated <script>
  const jsRun = /(?:<script src="(js\/[^"]+)"><\/script>\n)+/;
  const jsMatch = html.match(jsRun);
  if (!jsMatch) throw new Error('No application <script> tags found in src/index.html');
  const jsFiles = [...jsMatch[0].matchAll(/src="([^"]+)"/g)].map((m) => m[1]);
  const js = jsFiles.map(readScript).join('');
  html = html.replace(jsRun, () => '<script>\n' + js + '</script>\n');

  fs.mkdirSync(DIST, { recursive: true });
  fs.writeFileSync(OUT, html);

  const kb = (Buffer.byteLength(html) / 1024).toFixed(0);
  console.log(`Built ${path.relative(ROOT, OUT)} (${kb} KB) from ${cssFiles.length} stylesheets, ${jsFiles.length} scripts`);
}

build();
