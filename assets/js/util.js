// Small DOM / date / formatting helpers shared by every view.

import { icon } from './icons.js';

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** Escape a value for safe interpolation into an HTML template string. */
export function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

export const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
export const pct = (n) => clamp(Math.round(n), 0, 100);

/* ---------------------------------------------------------------- dates */

/** Local (not UTC) YYYY-MM-DD key. Using UTC would roll the day over at the
 *  wrong moment for anyone east or west of Greenwich. */
export function dateKey(date = new Date()) {
  const d = date instanceof Date ? date : new Date(date);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function parseKey(key) {
  const [y, m, d] = String(key).split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

export function addDays(key, delta) {
  const d = parseKey(key);
  d.setDate(d.getDate() + delta);
  return dateKey(d);
}

export function daysBetween(fromKey, toKey) {
  return Math.round((parseKey(toKey) - parseKey(fromKey)) / 86400000);
}

/** Monday-based start of the ISO week containing `key`. */
export function weekStart(key) {
  const d = parseKey(key);
  const shift = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - shift);
  return dateKey(d);
}

export function weekLabel(key) {
  const s = parseKey(weekStart(key));
  const e = parseKey(addDays(weekStart(key), 6));
  return `${s.getMonth() + 1}/${s.getDate()} – ${e.getMonth() + 1}/${e.getDate()}`;
}

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];
export const weekdayName = (key) => WEEKDAYS[parseKey(key).getDay()];

export function formatDate(key) {
  const d = parseKey(key);
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}（${WEEKDAYS[d.getDay()]}）`;
}

/** Seconds -> m:ss (or h:mm:ss beyond an hour). */
export function formatClock(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

export function formatMinutes(mins) {
  const m = Math.round(mins);
  if (m < 60) return `${m} 分`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  return rest ? `${h} 小時 ${rest} 分` : `${h} 小時`;
}

export function formatBytes(bytes) {
  if (!bytes) return '0 KB';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/* ------------------------------------------------------------ feedback */

let toastTimer = null;
export function toast(message, kind = 'info') {
  let host = $('#toastHost');
  if (!host) {
    host = document.createElement('div');
    host.id = 'toastHost';
    document.body.appendChild(host);
  }
  host.innerHTML = `<div class="toast toast--${kind}">${esc(message)}</div>`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { host.innerHTML = ''; }, 2400);
}

/**
 * Open a modal sheet. `body` is trusted HTML built by the caller.
 * Returns { close, root }. `onMount(root, close)` wires the body up.
 */
export function openModal(title, body, onMount) {
  const backdrop = $('#modalBackdrop');
  const modal = $('#modal');
  modal.innerHTML = `
    <div class="modal__head">
      <h2>${esc(title)}</h2>
      <button class="icon-btn" data-close aria-label="關閉">${icon('close')}</button>
    </div>
    <div class="modal__body">${body}</div>`;
  backdrop.classList.remove('hidden');
  document.body.classList.add('is-locked');

  const close = () => {
    backdrop.classList.add('hidden');
    document.body.classList.remove('is-locked');
    modal.innerHTML = '';
    backdrop.removeEventListener('click', onBackdrop);
    document.removeEventListener('keydown', onKey);
  };
  const onBackdrop = (e) => { if (e.target === backdrop) close(); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };

  backdrop.addEventListener('click', onBackdrop);
  document.addEventListener('keydown', onKey);
  modal.querySelector('[data-close]').addEventListener('click', close);
  if (onMount) onMount(modal, close);
  const firstField = modal.querySelector('input, textarea, select');
  if (firstField) setTimeout(() => firstField.focus(), 60);
  return { close, root: modal };
}

/** Promise-based confirm that matches the app's styling. */
export function confirmDialog(title, message, confirmLabel = '確定') {
  return new Promise((resolve) => {
    let settled = false;
    const done = (value, close) => { if (!settled) { settled = true; resolve(value); } close(); };
    openModal(title, `
      <p class="muted" style="line-height:1.6">${esc(message)}</p>
      <div class="row row--end" style="margin-top:16px">
        <button class="btn btn--ghost" data-cancel>取消</button>
        <button class="btn btn--danger" data-ok>${esc(confirmLabel)}</button>
      </div>`, (root, close) => {
      root.querySelector('[data-ok]').addEventListener('click', () => done(true, close));
      root.querySelector('[data-cancel]').addEventListener('click', () => done(false, close));
      root.querySelector('[data-close]').addEventListener('click', () => done(false, () => {}));
    });
  });
}

/* --------------------------------------------------------------- misc */

export function download(filename, text, type = 'application/json') {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function debounce(fn, wait = 250) {
  let t = null;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
}

export const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) ||
  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

export const isStandalone = () => window.matchMedia('(display-mode: standalone)').matches ||
  window.navigator.standalone === true;
