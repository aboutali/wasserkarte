#!/usr/bin/env node
// Headless-browser tasks on the built pages (needs `npm install` and a Playwright Chromium).
//
//   node scripts/render.mjs smoke        load dist/index.html, fail on JS errors or broken UI
//   node scripts/render.mjs poster       build/poster.html -> dist/gewaesserstammbaum-a0.pdf
//   node scripts/render.mjs screenshots  dist/index.html -> docs/img/*.png
//
// CHROMIUM_PATH=/path/to/chrome overrides the Playwright-managed browser.
import { chromium } from 'playwright';
import { existsSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const page = (p) => pathToFileURL(resolve(ROOT, p)).href;
const launch = () => chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});

function need(p, hint) {
  if (!existsSync(resolve(ROOT, p))) { console.error(`${p} missing — run ${hint}`); process.exit(1); }
}

// Google Fonts are optional for these checks; ignore failed font requests (offline CI, sandboxes).
const isFontNoise = (msg) => /fonts\.(googleapis|gstatic)\.com|ERR_TUNNEL|ERR_NAME_NOT_RESOLVED|net::ERR/.test(msg);

async function smoke() {
  need('dist/index.html', 'make site');
  const browser = await launch();
  const problems = [];
  for (const [name, viewport] of [['desktop', { width: 1280, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    const ctx = await browser.newContext({ viewport });
    const p = await ctx.newPage();
    p.on('pageerror', (e) => problems.push(`${name}: ${e.message}`));
    p.on('console', (m) => { if (m.type() === 'error' && !isFontNoise(m.text())) problems.push(`${name}: console ${m.text()}`); });
    await p.goto(page('dist/index.html'));
    await p.waitForTimeout(800);
    const s = await p.evaluate(() => ({
      rows: document.querySelectorAll('#tree .row').length,
      rivers: document.querySelectorAll('#map path.riv').length,
      labels: document.querySelectorAll('#map text').length,
      figs: document.querySelectorAll('#figs .fig').length,
      placeholders: (document.body.innerHTML.match(/\{\{\w+\}\}/g) || []).length,
    }));
    if (s.rows < 3) problems.push(`${name}: tree shows ${s.rows} rows`);
    if (s.rivers < 100) problems.push(`${name}: map draws only ${s.rivers} courses`);
    if (s.figs !== 6) problems.push(`${name}: expected 6 key figures, got ${s.figs}`);
    if (s.placeholders) problems.push(`${name}: ${s.placeholders} unfilled {{placeholders}}`);
    // interaction: search, select, detail sheet
    await p.fill('#q', 'Mosel');
    await p.waitForTimeout(200);
    await p.click('.row[data-id="mosel"]');
    await p.waitForTimeout(400);
    const d = await p.evaluate(() => ({
      on: document.getElementById('detail').classList.contains('on'),
      name: document.getElementById('dname').textContent,
      path: document.getElementById('dpath').innerText,
      dimmed: document.querySelectorAll('#map .riv.dim').length,
    }));
    if (!d.on || d.name !== 'Mosel') problems.push(`${name}: detail sheet did not open for Mosel`);
    if (!/Rhein/.test(d.path)) problems.push(`${name}: Mosel ancestry should mention Rhein, got "${d.path}"`);
    if (d.dimmed < 50) problems.push(`${name}: selecting Mosel should dim the rest of the map`);
    console.log(`${name.padEnd(8)} rows ${s.rows}, courses ${s.rivers}, labels ${s.labels}, selection ok=${d.on}`);
    await ctx.close();
  }
  await browser.close();
  if (problems.length) { console.error('\nSMOKE TEST FAILED\n' + problems.map((x) => '  - ' + x).join('\n')); process.exit(1); }
  console.log('smoke test passed');
}

async function poster() {
  need('build/poster.html', 'make site');
  need('build/fonts/Spectral-Regular.ttf', 'python scripts/fetch_sources.py --fonts');
  mkdirSync(resolve(ROOT, 'dist'), { recursive: true });
  const browser = await launch();
  // 4500 px ≈ 1189 mm at 96 dpi: the poster script calibrates label sizes to this layout.
  const p = await browser.newPage({ viewport: { width: 4500, height: 3200 } });
  const errors = [];
  p.on('pageerror', (e) => errors.push(e.message));
  await p.goto(page('build/poster.html'));
  await p.waitForFunction(() => document.body.dataset.ready === '1', null, { timeout: 30000 });
  await p.evaluate(() => document.fonts.ready);
  const t = await p.evaluate(() => { const e = document.getElementById('tree'); return { sh: e.scrollHeight, ch: e.clientHeight }; });
  if (t.sh > t.ch + 2) console.warn(`warning: tree overflows its columns (${t.sh} > ${t.ch}px) — reduce row height in web/poster.template.html`);
  const out = resolve(ROOT, 'dist/gewaesserstammbaum-a0.pdf');
  await p.pdf({ path: out, width: '1189mm', height: '841mm', printBackground: true, pageRanges: '1' });
  await p.screenshot({ path: resolve(ROOT, 'build/poster-preview.png') });
  await browser.close();
  if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
  console.log('dist/gewaesserstammbaum-a0.pdf (preview: build/poster-preview.png)');
}

async function screenshots() {
  need('dist/index.html', 'make site');
  mkdirSync(resolve(ROOT, 'docs/img'), { recursive: true });
  const browser = await launch();
  const shots = [
    { file: 'tree.png', viewport: { width: 1280, height: 900 }, section: 'stammbaum' },
    { file: 'map.png', viewport: { width: 1280, height: 1500 }, section: 'karte' },
    { file: 'map-dark.png', viewport: { width: 1280, height: 1500 }, section: 'karte', dark: true },
    { file: 'mobile.png', viewport: { width: 390, height: 844 }, section: 'karte', scale: 2 },
  ];
  for (const s of shots) {
    const ctx = await browser.newContext({ viewport: s.viewport, deviceScaleFactor: s.scale || 1,
      colorScheme: s.dark ? 'dark' : 'light' });
    const p = await ctx.newPage();
    await p.goto(page('dist/index.html'));
    await p.waitForTimeout(600);
    await p.evaluate((id) => document.getElementById(id).scrollIntoView(), s.section);
    await p.waitForTimeout(500);
    await p.screenshot({ path: resolve(ROOT, 'docs/img', s.file) });
    await ctx.close();
    console.log('docs/img/' + s.file);
  }
  await browser.close();
}

const tasks = { smoke, poster, screenshots };
const task = tasks[process.argv[2]];
if (!task) { console.error('usage: node scripts/render.mjs smoke|poster|screenshots'); process.exit(2); }
await task();
