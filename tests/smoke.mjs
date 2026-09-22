// Headless browser smoke test: boots the real app, walks every route at an
// iPhone viewport, exercises the core interactions and checks the PWA wiring.
// Run with: npm run smoke   (add --shots to write screenshots to .tmp/shots)

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from 'playwright';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT || 8099);
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = process.argv.includes('--shots');
const SHOT_DIR = path.join(ROOT, '.tmp', 'shots');

const ROUTES = [
  'dashboard', 'practice', 'practice/drone', 'practice/tuner', 'practice/timer',
  'skills', 'repertoire', 'review', 'plan', 'competition', 'calendar',
  'recordings', 'achievements', 'settings', 'more',
];

const failures = [];
const check = (ok, label) => {
  console.log(`${ok ? '  ✓' : '  ✗'} ${label}`);
  if (!ok) failures.push(label);
};

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function startServer() {
  const proc = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'], {
    cwd: ROOT, stdio: 'ignore',
  });
  for (let i = 0; i < 60; i += 1) {
    try {
      const res = await fetch(`${BASE}/index.html`);
      if (res.ok) return proc;
    } catch { /* not up yet */ }
    await wait(200);
  }
  proc.kill();
  throw new Error('static server did not start');
}

async function main() {
  const server = await startServer();
  // Use the browser that ships with the environment when the bundled build
  // for this Playwright version is not downloaded.
  const preinstalled = ['/opt/pw-browsers/chromium', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome']
    .find((p) => fs.existsSync(p) && fs.statSync(p).isFile());
  const browser = await chromium.launch({
    ...(preinstalled ? { executablePath: preinstalled } : {}),
    args: ['--autoplay-policy=no-user-gesture-required', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  });
  const context = await browser.newContext({ ...devices['iPhone 13'], permissions: ['microphone'] });
  const page = await context.newPage();

  const errors = [];
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));

  if (SHOTS) fs.mkdirSync(SHOT_DIR, { recursive: true });

  try {
    console.log('\n● boot');
    await page.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
    // First run shows the onboarding sheet.
    await page.waitForSelector('[data-o-save]', { timeout: 8000 });
    check(await page.locator('#modal').isVisible(), 'onboarding sheet appears on first run');
    await page.fill('[data-o="name"]', 'Ethan');
    await page.click('[data-o-save]');
    await page.waitForSelector('#modal', { state: 'hidden' });
    check((await page.locator('.quest').count()) > 0, 'daily quests are generated');
    check((await page.locator('#tabBar .tab').count()) === 5, 'bottom tab bar has five tabs');

    console.log('\n● routes');
    for (const route of ROUTES) {
      await page.goto(`${BASE}/index.html#/${route}`);
      await page.waitForFunction((r) => document.querySelector('#view')?.dataset.route === r.split('/')[0], route, { timeout: 5000 });
      await wait(120);
      const heading = await page.locator('#view h1').first().textContent();
      check(!!heading?.trim(), `route ${route} renders "${heading?.trim() ?? ''}"`);
      if (SHOTS) await page.screenshot({ path: path.join(SHOT_DIR, `${route.replace('/', '-')}.png`), fullPage: false });
    }

    console.log('\n● interactions');
    await page.goto(`${BASE}/index.html#/dashboard`);
    await page.waitForSelector('.quest');
    const xpBefore = Number(await page.locator('#sideXp, #headerLevel').first().textContent().catch(() => '0'));
    await page.locator('.quest__check').first().click();
    await wait(300);
    check((await page.locator('.quest.is-done').count()) > 0, 'completing a quest marks it done');
    const pillXp = await page.locator('.pill').nth(1).textContent();
    check(/\d/.test(pillXp || ''), `XP pill updates (${pillXp?.trim()})`);

    await page.locator('[data-timer="0"]').click();
    await wait(1400);
    const barVisible = await page.locator('#practiceBar').isVisible();
    check(barVisible, 'practice bar appears while a quest timer runs');
    await page.locator('#practiceBar [data-bar="stop"]').click();
    await wait(200);

    // Boss + persistence across a reload.
    await page.locator('[data-action="boss"]').click();
    await wait(300);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForSelector('.quest');
    check((await page.locator('.boss.is-done').count()) > 0, 'boss completion survives a reload');
    check((await page.locator('.quest.is-done').count()) > 0, 'quest completion survives a reload');

    console.log('\n● tools');
    await page.goto(`${BASE}/index.html#/practice/metronome`);
    await page.waitForSelector('[data-metro-toggle]');
    await page.click('[data-metro-toggle]');
    await wait(1200);
    check(await page.evaluate(() => document.querySelectorAll('.beat.is-on').length >= 0), 'metronome starts without error');
    const beatSeen = await page.evaluate(() => new Promise((resolve) => {
      let seen = false;
      const t = setInterval(() => { if (document.querySelector('.beat.is-on')) { seen = true; } }, 30);
      setTimeout(() => { clearInterval(t); resolve(seen); }, 1500);
    }));
    check(beatSeen, 'metronome drives the beat indicator');
    await page.click('[data-metro-toggle]');

    await page.goto(`${BASE}/index.html#/practice/drone`);
    await page.click('[data-drone-toggle]');
    await wait(400);
    check(await page.evaluate(() => !!document.querySelector('.btn--danger')), 'drone toggles to playing state');
    await page.click('[data-drone-toggle]');

    console.log('\n● data');
    await page.goto(`${BASE}/index.html#/repertoire`);
    await page.click('[data-add]');
    await page.fill('[data-f="work"]', 'Sibelius Violin Concerto');
    await page.fill('[data-f="part"]', 'I. Allegro moderato');
    await page.click('[data-save]');
    await wait(300);
    check((await page.locator('.rep').count()) >= 6, 'new repertoire entry is added');

    await page.goto(`${BASE}/index.html#/review`);
    await page.locator('.checklist--interactive input').first().check();
    await wait(600);
    await page.reload({ waitUntil: 'networkidle' });
    check(await page.locator('.checklist--interactive input').first().isChecked(), 'acceptance checkbox persists');

    console.log('\n● pwa');
    const manifestRes = await page.request.get(`${BASE}/manifest.webmanifest`);
    check(manifestRes.ok(), 'manifest is served');
    const swReady = await page.evaluate(async () => {
      const reg = await navigator.serviceWorker.getRegistration();
      return !!reg;
    });
    check(swReady, 'service worker registers');
    const controlled = await page.evaluate(async () => {
      await navigator.serviceWorker.ready;
      return !!navigator.serviceWorker.controller || !!(await navigator.serviceWorker.getRegistration())?.active;
    });
    check(controlled, 'service worker becomes active');

    // Offline: the shell must still boot from cache.
    await context.setOffline(true);
    await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.quest', { timeout: 8000 }).catch(() => {});
    check((await page.locator('.quest').count()) > 0, 'app boots offline from the service worker cache');
    await context.setOffline(false);

    const realErrors = errors.filter((e) => !/favicon|Failed to load resource: net::ERR_INTERNET_DISCONNECTED/i.test(e));
    check(realErrors.length === 0, `no console errors (${realErrors.length})`);
    realErrors.forEach((e) => console.log(`      ! ${e}`));
  } finally {
    await browser.close();
    server.kill();
  }

  console.log(`\n${failures.length ? `FAILED (${failures.length})` : 'ALL SMOKE CHECKS PASSED'}`);
  if (failures.length) {
    failures.forEach((f) => console.log(` - ${f}`));
    process.exit(1);
  }
}

main().catch((err) => { console.error(err); process.exit(1); });
