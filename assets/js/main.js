// App bootstrap: navigation shell, service worker, day rollover, practice bar.

import { state, stats, ensureToday, subscribe, onAchievement, todayKey, setProfile, saveNow } from './state.js';
import { registerAll, start, navigate, render as renderRoute, onRouteChange } from './router.js';
import { applyTheme, watchSystemTheme } from './theme.js';
import { session } from './session.js';
import { audio } from './audio.js';
import { $, $$, esc, toast, formatClock, isIOS, isStandalone, openModal } from './util.js';
import { APP_VERSION } from './version.js';

import { dashboardView } from './views/dashboard.js';
import { practiceView } from './views/practice.js';
import { skillsView } from './views/skills.js';
import { repertoireView } from './views/repertoire.js';
import { reviewView } from './views/review.js';
import { planView } from './views/plan.js';
import { competitionView } from './views/competition.js';
import { calendarView } from './views/calendar.js';
import { recordingsView } from './views/recordings.js';
import { achievementsView } from './views/achievements.js';
import { settingsView } from './views/settings.js';
import { moreView } from './views/more.js';

const VIEWS = [
  dashboardView, practiceView, skillsView, repertoireView, reviewView,
  planView, competitionView, calendarView, recordingsView, achievementsView,
  settingsView, moreView,
];

// The five tabs that live in the bottom bar on phones.
const PRIMARY = ['dashboard', 'practice', 'skills', 'review', 'more'];

/* ------------------------------------------------------------- chrome */

function renderNav() {
  const side = $('#sideNav');
  const tabs = $('#tabBar');
  const sideItems = [dashboardView, practiceView, skillsView, repertoireView, reviewView,
    planView, competitionView, calendarView, recordingsView, achievementsView, settingsView];

  side.innerHTML = sideItems.map((v) => `
    <button class="nav-btn" data-nav="${v.id}">
      <span class="nav-btn__icon">${v.icon}</span><span>${esc(v.label)}</span>
    </button>`).join('');

  tabs.innerHTML = PRIMARY.map((id) => {
    const v = VIEWS.find((x) => x.id === id);
    return `<button class="tab" data-nav="${v.id}">
      <span class="tab__icon">${v.icon}</span><span class="tab__label">${esc(v.label)}</span>
    </button>`;
  }).join('');

  $$('[data-nav]').forEach((btn) => btn.addEventListener('click', () => {
    navigate(btn.dataset.nav);
    document.body.classList.remove('nav-open');
  }));
}

function syncNav(route) {
  const id = route?.id;
  $$('[data-nav]').forEach((btn) => btn.classList.toggle('is-on', btn.dataset.nav === id));
  // Secondary pages keep "更多" highlighted in the bottom bar.
  if (id && !PRIMARY.includes(id)) {
    $('#tabBar [data-nav="more"]')?.classList.add('is-on');
  }
}

function syncHeader() {
  const s = stats();
  $('#sideXp').textContent = s.xp;
  $('#sideLevel').textContent = `LV.${s.level}`;
  $('#sideStreak').textContent = s.streak;
  $('#headerStreak').textContent = `🔥 ${s.streak}`;
  $('#headerLevel').textContent = `LV.${s.level}`;
}

/* -------------------------------------------------------- practice bar */

function renderPracticeBar() {
  const bar = $('#practiceBar');
  const active = session.active;
  const metroOn = audio.metroRunning;
  const droneOn = audio.droneRunning;

  if (!active && !metroOn && !droneOn) { bar.hidden = true; bar.innerHTML = ''; return; }

  bar.hidden = false;
  bar.innerHTML = `
    ${active ? `
      <button class="bar-btn" data-bar="toggle">${session.running ? '⏸' : '▶︎'}</button>
      <div class="bar-info">
        <strong data-bar-time>${formatClock(session.elapsed())}</strong>
        <span>${esc(active.title)}</span>
      </div>
      <button class="bar-btn" data-bar="stop">■</button>` : '<div class="bar-info"><strong>練習工具運作中</strong><span>點擊調整</span></div>'}
    ${metroOn ? '<button class="bar-chip" data-bar="metro">🥁 停止</button>' : ''}
    ${droneOn ? '<button class="bar-chip" data-bar="drone">🎵 停止</button>' : ''}`;

  $$('[data-bar]', bar).forEach((btn) => btn.addEventListener('click', () => {
    const action = btn.dataset.bar;
    if (action === 'toggle') session.toggle({ freeform: !session.active });
    if (action === 'stop') {
      const total = session.stop();
      if (total > 30) toast(`已記錄 ${Math.round(total / 60)} 分鐘`, 'good');
      renderRoute();
    }
    if (action === 'metro') { audio.stopMetronome(); renderPracticeBar(); }
    if (action === 'drone') { audio.stopDrone(); renderPracticeBar(); }
  }));
}

/* ------------------------------------------------------ day lifecycle */

let lastSeenDay = todayKey();
function checkDayRollover() {
  const key = todayKey();
  if (key === lastSeenDay) return;
  lastSeenDay = key;
  if (session.active) session.stop();
  ensureToday();
  saveNow();
  toast('新的一天，已產生今日任務');
  renderRoute();
}

/* --------------------------------------------------------- onboarding */

function maybeOnboard() {
  const hasHistory = Object.keys(state.days).length > 1 || state.profile.name;
  if (hasHistory) return;
  openModal('歡迎使用 Violin Quest Pro', `
    <p class="muted">先設定三件事，系統就能開始幫你排每天的訓練菜單。</p>
    <label class="field"><span class="field__label">你的名字</span><input class="input" data-o="name" placeholder="Ethan"></label>
    <label class="field"><span class="field__label">目前主曲目</span><input class="input" data-o="mainWork" value="${esc(state.profile.mainWork)}"></label>
    <label class="field"><span class="field__label">每天可練分鐘</span><input class="input" type="number" min="30" max="600" step="15" data-o="dailyMinutes" value="${state.profile.dailyMinutes}"></label>
    <div class="row row--end" style="margin-top:14px"><button class="btn btn--primary" data-o-save>開始訓練</button></div>`,
  (modal, close) => {
    modal.querySelector('[data-o-save]').addEventListener('click', () => {
      setProfile({
        name: modal.querySelector('[data-o="name"]').value.trim(),
        mainWork: modal.querySelector('[data-o="mainWork"]').value.trim() || state.profile.mainWork,
        dailyMinutes: Number(modal.querySelector('[data-o="dailyMinutes"]').value) || 210,
      });
      const day = state.days[todayKey()];
      if (day) day.tasks = [];
      ensureToday();
      saveNow();
      close();
      renderRoute();
      toast('今日任務已產生，開始吧', 'good');
    });
  });
}

/* ---------------------------------------------------- service worker */

function registerServiceWorker() {
  if (!('serviceWorker' in navigator) || location.protocol === 'file:') return;
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('./sw.js', { scope: './' });
      reg.addEventListener('updatefound', () => {
        const installing = reg.installing;
        if (!installing) return;
        installing.addEventListener('statechange', () => {
          if (installing.state === 'installed' && navigator.serviceWorker.controller) {
            showUpdateBanner(reg);
          }
        });
      });
    } catch (err) {
      console.warn('[sw] registration failed', err);
    }
  });

  let refreshing = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (refreshing) return;
    refreshing = true;
    location.reload();
  });
}

function showUpdateBanner(reg) {
  const banner = $('#updateBanner');
  banner.hidden = false;
  banner.querySelector('[data-update-now]').addEventListener('click', () => {
    reg.waiting?.postMessage({ type: 'SKIP_WAITING' });
    banner.hidden = true;
  });
  banner.querySelector('[data-update-later]').addEventListener('click', () => { banner.hidden = true; });
}

/* ---------------------------------------------------------------- boot */

function boot() {
  applyTheme(state.settings.theme || 'auto');
  watchSystemTheme(() => state.settings.theme || 'auto');
  audio.a4 = state.settings.a4 || 440;

  ensureToday();
  saveNow();

  registerAll(VIEWS);
  renderNav();
  onRouteChange((route) => { syncNav(route); syncHeader(); });
  start();

  subscribe(() => { syncHeader(); renderPracticeBar(); });
  session.subscribe(() => renderPracticeBar());
  window.addEventListener('vq:audio-changed', renderPracticeBar);
  onAchievement((a) => toast(`🏅 解鎖成就：${a.name}`, 'good'));

  setInterval(() => {
    checkDayRollover();
    const label = $('[data-bar-time]');
    if (label && session.running) label.textContent = formatClock(session.elapsed());
  }, 1000);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') checkDayRollover();
  });

  $('#menuBtn').addEventListener('click', () => document.body.classList.toggle('nav-open'));
  $('#navScrim').addEventListener('click', () => document.body.classList.remove('nav-open'));

  // iOS only lets audio start inside a gesture; warm the context up on the
  // first touch so the metronome is instant when it is actually needed.
  const warm = () => { audio.ensure(); document.removeEventListener('touchend', warm); document.removeEventListener('click', warm); };
  document.addEventListener('touchend', warm, { passive: true });
  document.addEventListener('click', warm);

  syncHeader();
  renderPracticeBar();
  registerServiceWorker();
  maybeOnboard();

  document.body.classList.toggle('is-standalone', isStandalone());
  document.body.classList.toggle('is-ios', isIOS());
  console.info(`Violin Quest Pro ${APP_VERSION}`);
}

boot();
