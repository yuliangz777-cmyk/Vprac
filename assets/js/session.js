// A single app-wide practice timer. It survives navigation, so you can start a
// quest, jump to the metronome, and the clock keeps running in the bottom bar.

import { addTaskTime, addExtraMinutes, todayKey, state } from './state.js';
import { wakeLock } from './audio.js';

const listeners = new Set();

export const session = {
  active: null, // { dayKey, taskIndex, title, startedAt, accumulated, freeform }

  subscribe(fn) { listeners.add(fn); fn(this.active); return () => listeners.delete(fn); },

  _emit() { listeners.forEach((fn) => fn(this.active)); },

  elapsed() {
    if (!this.active) return 0;
    const running = this.active.startedAt ? (Date.now() - this.active.startedAt) / 1000 : 0;
    return this.active.accumulated + running;
  },

  get running() { return !!this.active?.startedAt; },

  start({ taskIndex = -1, title = '自由練習', freeform = false } = {}) {
    if (this.active && (this.active.taskIndex !== taskIndex || this.active.freeform !== freeform)) {
      this.stop();
    }
    if (!this.active) {
      this.active = { dayKey: todayKey(), taskIndex, title, startedAt: Date.now(), accumulated: 0, freeform };
    } else if (!this.active.startedAt) {
      this.active.startedAt = Date.now();
    }
    if (state.settings.keepAwake !== false) wakeLock.request();
    this._tick();
    this._emit();
  },

  pause() {
    if (!this.active?.startedAt) return;
    this.active.accumulated = this.elapsed();
    this.active.startedAt = null;
    this._flush();
    this._emit();
  },

  toggle(opts) {
    if (this.running) this.pause(); else this.start(opts);
  },

  /** Stop, persisting whatever has not been written yet. */
  stop() {
    if (!this.active) return 0;
    const total = this.elapsed();
    this._flush();
    this.active = null;
    wakeLock.release();
    clearTimeout(this._timer);
    this._emit();
    return total;
  },

  /** Write accumulated seconds into state and reset the accumulator. */
  _flush() {
    if (!this.active) return;
    const seconds = Math.round(this.active.accumulated - (this.active.saved || 0));
    if (seconds <= 0) return;
    if (this.active.freeform || this.active.taskIndex < 0) {
      addExtraMinutes(seconds / 60, this.active.dayKey);
    } else {
      addTaskTime(this.active.taskIndex, seconds, this.active.dayKey);
    }
    this.active.saved = this.active.accumulated;
  },

  /** Persist every 30s so a crash or a closed tab loses at most half a minute. */
  _tick() {
    clearTimeout(this._timer);
    if (!this.running) return;
    this._timer = setTimeout(() => {
      if (!this.running) return;
      this.active.accumulated = this.elapsed();
      this.active.startedAt = Date.now();
      this._flush();
      this._tick();
    }, 30000);
  },
};

// Do not silently lose time when the app is closed or backgrounded.
window.addEventListener('pagehide', () => { if (session.running) session.pause(); });
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden' && session.running) {
    session.active.accumulated = session.elapsed();
    session.active.startedAt = Date.now();
    session._flush();
  }
});
