// Unit tests for the pure logic: dates, XP curve, adaptive planning, schema
// migration, streaks, pitch detection, and PWA asset wiring.
// Run with: npm test   (node --test, no dependencies)

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/* A minimal localStorage so state.js can be imported outside a browser. */
class MemoryStorage {
  constructor() { this.map = new Map(); }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
  setItem(k, v) { this.map.set(k, String(v)); }
  removeItem(k) { this.map.delete(k); }
  clear() { this.map.clear(); }
}
globalThis.localStorage = new MemoryStorage();

const util = await import('../assets/js/util.js');
const content = await import('../assets/js/content.js');
const stateModule = await import('../assets/js/state.js');
const audio = await import('../assets/js/audio.js');
const { APP_VERSION } = await import('../assets/js/version.js');

/* ------------------------------------------------------------- dates */

test('dateKey uses local time, not UTC', () => {
  const d = new Date(2026, 0, 5, 23, 30); // 5 Jan 2026, local 23:30
  assert.equal(util.dateKey(d), '2026-01-05');
});

test('addDays and daysBetween cross month and year boundaries', () => {
  assert.equal(util.addDays('2026-02-28', 1), '2026-03-01'); // 2026 is not a leap year
  assert.equal(util.addDays('2025-12-31', 1), '2026-01-01');
  assert.equal(util.daysBetween('2026-01-01', '2026-03-01'), 59);
});

test('weekStart snaps to Monday', () => {
  assert.equal(util.weekStart('2026-09-03'), '2026-08-31'); // Thu -> Mon
  assert.equal(util.weekStart('2026-08-31'), '2026-08-31');
});

test('formatClock renders minutes and hours', () => {
  assert.equal(util.formatClock(65), '1:05');
  assert.equal(util.formatClock(3725), '1:02:05');
});

/* ---------------------------------------------------------- XP curve */

test('level thresholds are strictly increasing and start at 1', () => {
  assert.equal(content.levelFromXp(0), 1);
  let prev = -1;
  for (let l = 1; l <= 20; l += 1) {
    const need = content.xpForLevel(l);
    assert.ok(need > prev, `level ${l} threshold must increase`);
    prev = need;
    assert.equal(content.levelFromXp(need), l);
    if (l > 1) assert.equal(content.levelFromXp(need - 1), l - 1);
  }
});

test('levelProgress reports a fraction inside the current band', () => {
  const p = content.levelProgress(500);
  assert.ok(p.ratio >= 0 && p.ratio < 1);
  assert.equal(p.into + p.base, 500);
});

/* ------------------------------------------------------ day planning */

test('buildDayPlan favours the weakest skills', () => {
  const skills = { intonation: 10, bow: 12, shifting: 15, rhythm: 90, tone: 92, musicality: 93, stage: 94, stamina: 95 };
  const plan = content.buildDayPlan({ skills, minutes: 210, rand: () => 0.5 });
  const weakCats = plan.filter((t) => ['intonation', 'bow', 'shifting'].includes(t.cat));
  assert.ok(weakCats.length >= plan.length / 2, 'most quests should target weak skills');
});

test('buildDayPlan stays inside the available time and never repeats a quest', () => {
  const skills = Object.fromEntries(content.SKILL_KEYS.map((k) => [k, 50]));
  for (const minutes of [60, 120, 210, 360]) {
    const plan = content.buildDayPlan({ skills, minutes, rand: () => 0.5 });
    assert.ok(plan.length > 0, `plan for ${minutes} minutes should not be empty`);
    const ids = plan.map((t) => t.id);
    assert.equal(new Set(ids).size, ids.length, 'no duplicate quests');
    const total = plan.reduce((a, t) => a + t.mins, 0);
    assert.ok(total <= minutes + 45, `plan of ${total} min should respect a ${minutes} min budget`);
  }
});

test('buildDayPlan re-issues quests that were left unfinished', () => {
  const skills = Object.fromEntries(content.SKILL_KEYS.map((k) => [k, 50]));
  const recentDays = [{ tasks: [{ id: 'memory', done: false }, { id: 'benchmark', done: false }] }];
  const plan = content.buildDayPlan({ skills, recentDays, minutes: 240, rand: () => 0.1 });
  assert.ok(plan.some((t) => t.id === 'memory' || t.id === 'benchmark'));
});

test('buildDayPlan substitutes the main work into quest descriptions', () => {
  const skills = Object.fromEntries(content.SKILL_KEYS.map((k) => [k, 50]));
  const plan = content.buildDayPlan({ skills, minutes: 300, mainWork: 'Sibelius', rand: () => 0.9 });
  assert.ok(plan.every((t) => !t.desc.includes('主曲目')));
});

/* -------------------------------------------------------- phase gates */

test('phase gates clear only when every requirement is met', () => {
  const strong = {
    skills: Object.fromEntries(content.SKILL_KEYS.map((k) => [k, 100])),
    repertoire: [{ readiness: 100 }],
    bestStreak: 400,
  };
  const weak = {
    skills: Object.fromEntries(content.SKILL_KEYS.map((k) => [k, 10])),
    repertoire: [{ readiness: 0 }],
    bestStreak: 0,
  };
  assert.equal(content.phaseProgress(content.PHASES[0], strong).complete, true);
  assert.equal(content.phaseProgress(content.PHASES[0], weak).complete, false);
  assert.equal(content.currentPhaseIndex(weak), 0);
  assert.equal(content.currentPhaseIndex(strong), content.PHASES.length - 1);
});

/* ---------------------------------------------------------- migration */

test('migrate upgrades a v1 prototype save', () => {
  const legacy = {
    profile: { name: 'Ethan', dailyMinutes: 180 },
    xp: 400,
    skills: { intonation: 61 },
    repertoire: [{ work: 'Bach', part: 'Chaconne', status: 'active', readiness: 70 }],
    days: {
      '2026-08-01': {
        tasks: [{ id: 'scale', cat: 'intonation', title: '音階', desc: '', mins: 25, xp: 25, done: true }],
        checks: { 0: true, w1: true },
        notes: 'ok',
        bossDone: true,
      },
      'not-a-date': { tasks: [] },
    },
    competitions: [{ name: 'X', date: '2026-09-01' }],
  };
  const migrated = stateModule.migrate(legacy);
  assert.equal(migrated.schema, stateModule.SCHEMA);
  assert.equal(migrated.profile.name, 'Ethan');
  assert.equal(migrated.profile.dailyMinutes, 180);
  assert.equal(migrated.skills.intonation, 61);
  assert.equal(migrated.skills.bow, 48, 'missing skills fall back to defaults');
  assert.ok(migrated.repertoire[0].id, 'repertoire entries get ids');
  assert.ok(migrated.competitions[0].id);
  const day = migrated.days['2026-08-01'];
  assert.equal(day.checks[0], true);
  assert.equal(day.weekChecks[1], true, 'w-prefixed checks become weekly checks');
  assert.equal(day.boss.done, true);
  assert.equal(migrated.days['not-a-date'], undefined, 'invalid day keys are dropped');
  assert.ok(migrated.acceptance.daily.length > 0);
});

test('migrate tolerates junk input', () => {
  for (const input of [null, undefined, 42, 'nope', {}, { days: null }]) {
    const out = stateModule.migrate(input);
    assert.equal(out.schema, stateModule.SCHEMA);
    assert.equal(typeof out.days, 'object');
    assert.equal(content.SKILL_KEYS.every((k) => typeof out.skills[k] === 'number'), true);
  }
});

/* ----------------------------------------------------- streak and XP */

test('streak counts back from today and stops at the first gap', () => {
  const s = stateModule.state;
  const today = stateModule.todayKey();
  const full = (n) => ({ ...stateModule.emptyDay(), tasks: Array.from({ length: n }, () => ({ id: 'x', mins: 10, xp: 10, done: true })) });
  s.days = {
    [today]: full(3),
    [util.addDays(today, -1)]: full(3),
    [util.addDays(today, -2)]: full(3),
    [util.addDays(today, -4)]: full(3),
  };
  assert.equal(stateModule.computeStreak(), 3);
  assert.equal(stateModule.computeBestStreak(), 3);

  // A day below the completion ratio breaks the run.
  s.days[util.addDays(today, -1)].tasks.forEach((t) => { t.done = false; });
  assert.equal(stateModule.computeStreak(), 1);
});

test('XP is derived from recorded work, so undoing a task removes its XP', () => {
  const s = stateModule.state;
  const today = stateModule.todayKey();
  s.days = { [today]: { ...stateModule.emptyDay(), tasks: [{ id: 'a', mins: 10, xp: 25, done: true }, { id: 'b', mins: 10, xp: 30, done: true }] } };
  s.weeklyReviews = [];
  assert.equal(stateModule.computeXp(), 55);
  s.days[today].boss = { done: true, score: 100, notes: '' };
  assert.equal(stateModule.computeXp(), 55 + 60 + 40);
  s.days[today].tasks[0].done = false;
  assert.equal(stateModule.computeXp(), 30 + 60 + 40);
});

test('dayMinutes prefers measured time over the estimate', () => {
  const day = { ...stateModule.emptyDay(), tasks: [{ id: 'a', mins: 20, xp: 10, done: true, spent: 600 }, { id: 'b', mins: 30, xp: 10, done: true, spent: 0 }], extraMinutes: 5 };
  assert.equal(stateModule.dayMinutes(day), 10 + 30 + 5);
});

/* ------------------------------------------------------------- audio */

test('autoCorrelate recovers a synthesised pitch', () => {
  const sampleRate = 44100;
  for (const hz of [196, 293.66, 440, 659.26]) {
    const buf = new Float32Array(2048);
    for (let i = 0; i < buf.length; i += 1) {
      // fundamental plus a couple of partials, like a bowed string
      buf[i] = 0.6 * Math.sin((2 * Math.PI * hz * i) / sampleRate)
        + 0.25 * Math.sin((4 * Math.PI * hz * i) / sampleRate)
        + 0.1 * Math.sin((6 * Math.PI * hz * i) / sampleRate);
    }
    const found = audio.autoCorrelate(buf, sampleRate);
    assert.ok(Math.abs(found - hz) / hz < 0.01, `expected ~${hz} Hz, got ${found}`);
  }
});

test('autoCorrelate rejects silence', () => {
  assert.equal(audio.autoCorrelate(new Float32Array(2048), 44100), -1);
});

test('note naming and A4 calibration agree', () => {
  assert.equal(audio.midiToFreq(69), 440);
  assert.equal(Math.round(audio.midiToFreq(69, 442)), 442);
  const note = audio.freqToNote(440);
  assert.equal(note.name, 'A');
  assert.equal(note.octave, 4);
  assert.equal(note.cents, 0);
  assert.ok(Math.abs(audio.freqToNote(445).cents - 20) < 2, 'sharp readings report positive cents');
});

/* ---------------------------------------------------------- PWA files */

test('every file the service worker precaches exists', () => {
  const sw = fs.readFileSync(path.join(ROOT, 'sw.js'), 'utf8');
  const list = sw.slice(sw.indexOf('const PRECACHE'), sw.indexOf('];', sw.indexOf('const PRECACHE')));
  const files = [...list.matchAll(/'\.\/([^']+)'/g)].map((m) => m[1]);
  assert.ok(files.length > 20, 'precache list should cover the app shell');
  for (const file of files) {
    assert.ok(fs.existsSync(path.join(ROOT, file)), `missing precached file: ${file}`);
  }
});

test('every ES module in assets/js is precached', () => {
  const sw = fs.readFileSync(path.join(ROOT, 'sw.js'), 'utf8');
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (
    e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]
  ));
  for (const file of walk(path.join(ROOT, 'assets', 'js'))) {
    const rel = `./${path.relative(ROOT, file).split(path.sep).join('/')}`;
    assert.ok(sw.includes(`'${rel}'`), `service worker does not precache ${rel}`);
  }
});

test('service worker cache version matches the app version', () => {
  const sw = fs.readFileSync(path.join(ROOT, 'sw.js'), 'utf8');
  const match = sw.match(/CACHE_VERSION\s*=\s*'([^']+)'/);
  assert.ok(match, 'sw.js must define CACHE_VERSION');
  assert.equal(match[1], APP_VERSION);
});

test('manifest points at icons that exist and covers the install requirements', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'manifest.webmanifest'), 'utf8'));
  assert.equal(manifest.display, 'standalone');
  assert.ok(manifest.name && manifest.short_name);
  assert.ok(manifest.icons.some((i) => i.sizes === '512x512' && i.purpose === 'any'));
  assert.ok(manifest.icons.some((i) => i.purpose === 'maskable'));
  for (const icon of manifest.icons) {
    const file = path.join(ROOT, icon.src.replace('./', ''));
    assert.ok(fs.existsSync(file), `missing icon ${icon.src}`);
    const [w, h] = icon.sizes.split('x').map(Number);
    const buf = fs.readFileSync(file);
    assert.equal(buf.readUInt32BE(16), w, `${icon.src} width`);
    assert.equal(buf.readUInt32BE(20), h, `${icon.src} height`);
  }
});

test('index.html carries the iOS home-screen tags', () => {
  const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
  for (const needle of [
    'rel="manifest"',
    'apple-touch-icon',
    'name="apple-mobile-web-app-capable" content="yes"',
    'viewport-fit=cover',
    'type="module"',
  ]) {
    assert.ok(html.includes(needle), `index.html should contain ${needle}`);
  }
});
