// Persistent application state: schema, migration, derived stats, mutations.

import { dateKey, addDays, weekStart, uid, clamp, debounce } from './util.js';
import {
  SKILL_KEYS, DAILY_ACCEPTANCE, WEEKLY_ACCEPTANCE, ACHIEVEMENTS,
  buildDayPlan, levelFromXp, levelProgress,
} from './content.js';

export const STORAGE_KEY = 'violinQuestPro.v2';
const LEGACY_KEY = 'violinQuestProV1';
export const SCHEMA = 2;

/** A day counts toward the streak once this share of its quests is done. */
export const DAY_COMPLETE_RATIO = 0.6;

export const XP_RULES = { boss: 60, bossScore: 40, dailyChecklist: 30, weeklyReview: 40 };

export function defaultState() {
  return {
    schema: SCHEMA,
    createdAt: new Date().toISOString(),
    profile: {
      name: '',
      target: '國際小提琴大賽 Final / Prize',
      dailyMinutes: 210,
      weeklyDays: 6,
      mainWork: 'Beethoven Violin Concerto Op.61 第一樂章',
      cadenza: 'Auer',
      teacher: '',
      performanceDate: '',
      competitionDate: '',
      competitionName: '',
    },
    settings: { theme: 'auto', a4: 440, haptics: true, keepAwake: true, autoPlan: true },
    skills: { intonation: 52, bow: 48, shifting: 50, rhythm: 65, tone: 55, musicality: 58, stage: 45, stamina: 50 },
    skillHistory: [],
    repertoire: [
      { id: uid('rep'), work: 'Beethoven Violin Concerto Op.61', part: '第一樂章＋Auer Cadenza', status: 'active', readiness: 48, notes: '' },
      { id: uid('rep'), work: 'J.S. Bach 無伴奏', part: '目前主修樂章', status: 'active', readiness: 45, notes: '' },
      { id: uid('rep'), work: 'Mozart Concerto', part: '待建立', status: 'planned', readiness: 10, notes: '' },
      { id: uid('rep'), work: 'Paganini Caprices', part: '待建立', status: 'planned', readiness: 5, notes: '' },
      { id: uid('rep'), work: '大型奏鳴曲', part: '待建立', status: 'planned', readiness: 10, notes: '' },
    ],
    days: {},
    weeklyReviews: [],
    competitions: [],
    achievements: [],
    acceptance: { daily: [...DAILY_ACCEPTANCE], weekly: [...WEEKLY_ACCEPTANCE] },
  };
}

export function emptyDay() {
  return { tasks: [], checks: {}, weekChecks: {}, notes: '', nextFocus: '', boss: { done: false, score: 0, notes: '' }, extraMinutes: 0, recordings: [] };
}

/* ------------------------------------------------------------ storage */

function readRaw(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    console.warn('[state] read failed', err);
    return null;
  }
}

/** Bring a v1 prototype save (or a partial v2 save) up to the current schema. */
export function migrate(raw) {
  const base = defaultState();
  if (!raw || typeof raw !== 'object') return base;

  const out = { ...base, ...raw, schema: SCHEMA };
  out.profile = { ...base.profile, ...(raw.profile || {}) };
  out.settings = { ...base.settings, ...(raw.settings || {}) };
  out.skills = { ...base.skills, ...(raw.skills || {}) };
  SKILL_KEYS.forEach((k) => { out.skills[k] = clamp(Number(out.skills[k]) || 0, 0, 100); });
  out.acceptance = {
    daily: (raw.acceptance?.daily?.length ? raw.acceptance.daily : base.acceptance.daily).slice(),
    weekly: (raw.acceptance?.weekly?.length ? raw.acceptance.weekly : base.acceptance.weekly).slice(),
  };
  out.repertoire = (Array.isArray(raw.repertoire) ? raw.repertoire : base.repertoire).map((r) => ({
    id: r.id || uid('rep'),
    work: r.work || '未命名作品',
    part: r.part || '',
    status: r.status || 'planned',
    readiness: clamp(Number(r.readiness) || 0, 0, 100),
    notes: r.notes || '',
  }));
  out.skillHistory = Array.isArray(raw.skillHistory) ? raw.skillHistory : [];
  out.weeklyReviews = (Array.isArray(raw.weeklyReviews) ? raw.weeklyReviews : []).map((w) => ({
    id: w.id || uid('wk'), date: w.date || dateKey(), wins: w.wins || '', fixes: w.fixes || '',
  }));
  out.competitions = (Array.isArray(raw.competitions) ? raw.competitions : []).map((c) => ({
    id: c.id || uid('cmp'), name: c.name || '未命名賽事', date: c.date || '', result: c.result || '', notes: c.notes || '',
  }));
  out.achievements = Array.isArray(raw.achievements) ? raw.achievements : [];

  out.days = {};
  for (const [key, day] of Object.entries(raw.days || {})) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(key)) continue;
    const fresh = emptyDay();
    fresh.tasks = (day.tasks || []).map((t) => ({
      id: t.id, cat: t.cat, title: t.title, desc: t.desc,
      mins: Number(t.mins) || 15, xp: Number(t.xp) || 10,
      tools: t.tools || [], done: !!t.done, spent: Number(t.spent) || 0,
    }));
    fresh.notes = day.notes || '';
    fresh.nextFocus = day.nextFocus || '';
    fresh.extraMinutes = Number(day.extraMinutes) || 0;
    fresh.recordings = Array.isArray(day.recordings) ? day.recordings : [];
    // v1 stored daily checks as numeric keys and weekly ones as "w0", "w1"...
    const checks = day.checks || {};
    for (const [ck, cv] of Object.entries(checks)) {
      if (!cv) continue;
      if (String(ck).startsWith('w')) fresh.weekChecks[String(ck).slice(1)] = true;
      else fresh.checks[ck] = true;
    }
    Object.assign(fresh.weekChecks, day.weekChecks || {});
    if (day.boss) fresh.boss = { done: !!day.boss.done, score: Number(day.boss.score) || 0, notes: day.boss.notes || '' };
    else if (day.bossDone) fresh.boss = { done: true, score: Number(day.bossScore) || 0, notes: '' };
    out.days[key] = fresh;
  }
  return out;
}

export function loadState() {
  const raw = readRaw(STORAGE_KEY) || readRaw(LEGACY_KEY);
  return migrate(raw);
}

export let state = loadState();

const listeners = new Set();
export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }
export function emit() { listeners.forEach((fn) => fn(state)); }

let lastSaveError = null;
export function saveNow() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    lastSaveError = null;
  } catch (err) {
    lastSaveError = err;
    console.warn('[state] save failed', err);
  }
  return lastSaveError;
}
const saveDebounced = debounce(saveNow, 250);

// A debounced write can still be pending when the tab is closed or the app is
// swiped away on iOS, so flush on the way out.
if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => saveNow());
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') saveNow();
  });
}

/** Persist (debounced) and notify subscribers. */
export function commit({ immediate = false } = {}) {
  checkAchievements();
  if (immediate) saveNow(); else saveDebounced();
  emit();
}

export function replaceState(next) {
  state = migrate(next);
  ensureToday();
  saveNow();
  emit();
}

export function resetState() {
  state = defaultState();
  ensureToday();
  saveNow();
  emit();
}

/* --------------------------------------------------------------- days */

export const todayKey = () => dateKey();

export function getDay(key = todayKey()) {
  return state.days[key] || null;
}

/** Make sure today's entry exists and carries a quest plan. */
export function ensureToday() {
  const key = todayKey();
  if (!state.days[key]) state.days[key] = emptyDay();
  const day = state.days[key];
  if (!day.tasks.length && state.settings.autoPlan !== false) {
    day.tasks = planFor(key);
  }
  return day;
}

export function planFor(key = todayKey()) {
  const recent = Object.keys(state.days).filter((k) => k < key).sort().slice(-4).map((k) => state.days[k]);
  return buildDayPlan({
    skills: state.skills,
    recentDays: recent,
    minutes: state.profile.dailyMinutes,
    mainWork: state.profile.mainWork,
  });
}

export function rerollToday() {
  const day = ensureToday();
  const keepDone = day.tasks.filter((t) => t.done);
  const fresh = planFor().filter((t) => !keepDone.some((k) => k.id === t.id));
  day.tasks = [...keepDone, ...fresh].slice(0, 8);
  commit();
}

export function isDayComplete(day) {
  if (!day || !day.tasks.length) return false;
  const done = day.tasks.filter((t) => t.done).length;
  return done / day.tasks.length >= DAY_COMPLETE_RATIO;
}

export function dayMinutes(day) {
  if (!day) return 0;
  const fromTasks = day.tasks.reduce((a, t) => a + (t.spent ? t.spent / 60 : (t.done ? t.mins : 0)), 0);
  return Math.round(fromTasks + (day.extraMinutes || 0));
}

/** Streak walking backwards from today (today itself is optional). */
export function computeStreak() {
  let cursor = todayKey();
  if (!isDayComplete(state.days[cursor])) cursor = addDays(cursor, -1);
  let streak = 0;
  while (isDayComplete(state.days[cursor]) && streak < 3650) {
    streak += 1;
    cursor = addDays(cursor, -1);
  }
  return streak;
}

export function computeBestStreak() {
  const keys = Object.keys(state.days).filter((k) => isDayComplete(state.days[k])).sort();
  let best = 0; let run = 0; let prev = null;
  for (const key of keys) {
    run = prev && addDays(prev, 1) === key ? run + 1 : 1;
    prev = key;
    best = Math.max(best, run);
  }
  return best;
}

/* ------------------------------------------------------- derived stats */

export function computeXp() {
  let xp = 0;
  for (const day of Object.values(state.days)) {
    xp += day.tasks.filter((t) => t.done).reduce((a, t) => a + t.xp, 0);
    if (day.boss?.done) xp += XP_RULES.boss + Math.round((clamp(day.boss.score, 0, 100) / 100) * XP_RULES.bossScore);
    const dailyChecked = Object.values(day.checks || {}).filter(Boolean).length;
    if (dailyChecked >= state.acceptance.daily.length) xp += XP_RULES.dailyChecklist;
  }
  xp += state.weeklyReviews.length * XP_RULES.weeklyReview;
  return xp;
}

export function stats() {
  const days = Object.entries(state.days);
  const skillValues = Object.values(state.skills);
  const xp = computeXp();
  const totalMinutes = days.reduce((a, [, d]) => a + dayMinutes(d), 0);
  const perfectDays = days.filter(([, d]) => d.tasks.length && d.tasks.every((t) => t.done) && d.boss?.done).length;
  return {
    xp,
    ...levelProgress(xp),
    level: levelFromXp(xp),
    streak: computeStreak(),
    bestStreak: computeBestStreak(),
    totalMinutes,
    totalTasksDone: days.reduce((a, [, d]) => a + d.tasks.filter((t) => t.done).length, 0),
    activeDays: days.filter(([, d]) => dayMinutes(d) > 0).length,
    bossCount: days.filter(([, d]) => d.boss?.done).length,
    perfectDays,
    recordingCount: days.reduce((a, [, d]) => a + (d.recordings?.length || 0), 0),
    weeklyReviewCount: state.weeklyReviews.length,
    competitionCount: state.competitions.length,
    maxReadiness: state.repertoire.length ? Math.max(...state.repertoire.map((r) => r.readiness || 0)) : 0,
    minSkill: skillValues.length ? Math.min(...skillValues) : 0,
    avgSkill: skillValues.length ? skillValues.reduce((a, b) => a + b, 0) / skillValues.length : 0,
    skills: state.skills,
    repertoire: state.repertoire,
  };
}

export function weakSkills(count = 3) {
  return Object.entries(state.skills).sort((a, b) => a[1] - b[1]).slice(0, count).map(([k]) => k);
}

/** Minutes practised per day for the last `n` days, oldest first. */
export function minutesSeries(n = 14, endKey = todayKey()) {
  const out = [];
  for (let i = n - 1; i >= 0; i -= 1) {
    const key = addDays(endKey, -i);
    out.push({ key, minutes: dayMinutes(state.days[key]) });
  }
  return out;
}

export function newlyUnlockedAchievements() {
  const s = stats();
  return ACHIEVEMENTS.filter((a) => !state.achievements.includes(a.id) && a.test(s));
}

let achievementHook = null;
export function onAchievement(fn) { achievementHook = fn; }

function checkAchievements() {
  const unlocked = newlyUnlockedAchievements();
  if (!unlocked.length) return;
  unlocked.forEach((a) => state.achievements.push(a.id));
  if (achievementHook) unlocked.forEach((a) => achievementHook(a));
}

/* ----------------------------------------------------------- mutations */

export function toggleTask(index, key = todayKey()) {
  const day = state.days[key];
  const task = day?.tasks[index];
  if (!task) return;
  task.done = !task.done;
  if (task.done && !task.spent) task.spent = 0;
  commit();
}

export function addTaskTime(index, seconds, key = todayKey()) {
  const task = state.days[key]?.tasks[index];
  if (!task) return;
  task.spent = Math.max(0, (task.spent || 0) + seconds);
  commit();
}

export function addExtraMinutes(minutes, key = todayKey()) {
  const day = state.days[key] || ensureToday();
  day.extraMinutes = Math.max(0, (day.extraMinutes || 0) + minutes);
  commit();
}

export function setBoss(patch, key = todayKey()) {
  const day = state.days[key] || ensureToday();
  day.boss = { ...day.boss, ...patch };
  commit();
}

export function setCheck(kind, index, value, key = todayKey()) {
  const day = state.days[key] || ensureToday();
  const bucket = kind === 'weekly' ? day.weekChecks : day.checks;
  if (value) bucket[index] = true; else delete bucket[index];
  commit();
}

export function setDayField(field, value, key = todayKey()) {
  const day = state.days[key] || ensureToday();
  day[field] = value;
  commit();
}

export function setSkill(key, value) {
  state.skills[key] = clamp(Math.round(Number(value) || 0), 0, 100);
  commit();
}

export function snapshotSkills() {
  const today = todayKey();
  const entry = { date: today, skills: { ...state.skills } };
  const existing = state.skillHistory.findIndex((h) => h.date === today);
  if (existing >= 0) state.skillHistory[existing] = entry;
  else state.skillHistory.push(entry);
  state.skillHistory = state.skillHistory.slice(-52);
  commit({ immediate: true });
}

export function addRepertoire(entry) {
  state.repertoire.push({
    id: uid('rep'), work: entry.work || '未命名作品', part: entry.part || '',
    status: entry.status || 'planned', readiness: clamp(Number(entry.readiness) || 0, 0, 100), notes: entry.notes || '',
  });
  commit();
}

export function updateRepertoire(id, patch) {
  const item = state.repertoire.find((r) => r.id === id);
  if (!item) return;
  Object.assign(item, patch);
  if (patch.readiness !== undefined) item.readiness = clamp(Number(patch.readiness) || 0, 0, 100);
  commit();
}

export function removeRepertoire(id) {
  state.repertoire = state.repertoire.filter((r) => r.id !== id);
  commit();
}

export function addWeeklyReview(entry) {
  state.weeklyReviews.unshift({ id: uid('wk'), date: todayKey(), week: weekStart(todayKey()), ...entry });
  commit();
}

export function removeWeeklyReview(id) {
  state.weeklyReviews = state.weeklyReviews.filter((w) => w.id !== id);
  commit();
}

export function addCompetition(entry) {
  state.competitions.push({ id: uid('cmp'), ...entry });
  state.competitions.sort((a, b) => String(b.date).localeCompare(String(a.date)));
  commit();
}

export function updateCompetition(id, patch) {
  const item = state.competitions.find((c) => c.id === id);
  if (item) { Object.assign(item, patch); commit(); }
}

export function removeCompetition(id) {
  state.competitions = state.competitions.filter((c) => c.id !== id);
  commit();
}

export function setProfile(patch) {
  Object.assign(state.profile, patch);
  commit({ immediate: true });
}

export function setSetting(key, value) {
  state.settings[key] = value;
  commit({ immediate: true });
}

export function linkRecording(recordingId, key = todayKey()) {
  const day = state.days[key] || ensureToday();
  if (!day.recordings.includes(recordingId)) day.recordings.push(recordingId);
  commit();
}

export function unlinkRecording(recordingId) {
  for (const day of Object.values(state.days)) {
    day.recordings = (day.recordings || []).filter((r) => r !== recordingId);
  }
  commit();
}

export function exportJSON() {
  return JSON.stringify({ app: 'Violin Quest Pro', exportedAt: new Date().toISOString(), state }, null, 2);
}

export function importJSON(text) {
  const parsed = JSON.parse(text);
  const next = parsed.state || parsed;
  if (!next || typeof next !== 'object' || (!next.profile && !next.days)) {
    throw new Error('這不是 Violin Quest 備份檔');
  }
  replaceState(next);
}
