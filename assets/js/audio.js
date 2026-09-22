// Web Audio engine: metronome (lookahead scheduler), drone, and a
// microphone chromatic tuner. Everything is lazily created so that iOS only
// ever sees an AudioContext built inside a user gesture.

const NOTE_NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'];

export const OPEN_STRINGS = [
  { name: 'G', midi: 55 }, { name: 'D', midi: 62 }, { name: 'A', midi: 69 }, { name: 'E', midi: 76 },
];

export function midiToFreq(midi, a4 = 440) {
  return a4 * Math.pow(2, (midi - 69) / 12);
}

export function freqToNote(freq, a4 = 440) {
  const midiFloat = 69 + 12 * Math.log2(freq / a4);
  const midi = Math.round(midiFloat);
  const cents = Math.round((midiFloat - midi) * 100);
  return {
    midi,
    cents,
    name: NOTE_NAMES[((midi % 12) + 12) % 12],
    octave: Math.floor(midi / 12) - 1,
  };
}

class AudioEngine {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.a4 = 440;

    // metronome
    this.metroRunning = false;
    this.bpm = 72;
    this.beats = 4;
    this.subdivision = 1;
    this.accent = true;
    this.metroVolume = 0.7;
    this._nextNoteTime = 0;
    this._beatIndex = 0;
    this._timer = null;
    this._queue = [];
    this._beatHandlers = new Set();

    // drone
    this.droneNodes = null;
    this.droneVolume = 0.35;
    this.droneMidi = 69;
  }

  /** Must be called from a user gesture the first time. */
  ensure() {
    if (!this.ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      this.ctx = new Ctx();
      this.master = this.ctx.createGain();
      this.master.gain.value = 1;
      this.master.connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

  get supported() {
    return !!(window.AudioContext || window.webkitAudioContext);
  }

  /* ------------------------------------------------------- metronome */

  onBeat(fn) { this._beatHandlers.add(fn); return () => this._beatHandlers.delete(fn); }

  setTempo(bpm) {
    this.bpm = Math.max(20, Math.min(280, Math.round(bpm) || 60));
  }

  startMetronome() {
    if (this.metroRunning) return;
    const ctx = this.ensure();
    if (!ctx) return;
    this.metroRunning = true;
    this._beatIndex = 0;
    this._nextNoteTime = ctx.currentTime + 0.08;
    this._timer = setInterval(() => this._scheduler(), 25);
    this._raf = requestAnimationFrame(() => this._drainQueue());
  }

  stopMetronome() {
    this.metroRunning = false;
    clearInterval(this._timer);
    this._timer = null;
    this._queue.length = 0;
    if (this._raf) cancelAnimationFrame(this._raf);
    this._beatHandlers.forEach((fn) => fn({ beat: -1, bar: 0, sub: 0 }));
  }

  toggleMetronome() {
    if (this.metroRunning) this.stopMetronome(); else this.startMetronome();
    return this.metroRunning;
  }

  _scheduler() {
    const ctx = this.ctx;
    if (!ctx) return;
    const secondsPerBeat = 60 / this.bpm / this.subdivision;
    while (this._nextNoteTime < ctx.currentTime + 0.12) {
      const step = this._beatIndex % (this.beats * this.subdivision);
      const isDownbeat = step === 0;
      const isBeat = step % this.subdivision === 0;
      this._click(this._nextNoteTime, isDownbeat && this.accent ? 'accent' : (isBeat ? 'beat' : 'sub'));
      this._queue.push({ time: this._nextNoteTime, beat: Math.floor(step / this.subdivision), sub: step % this.subdivision });
      this._nextNoteTime += secondsPerBeat;
      this._beatIndex += 1;
    }
  }

  _drainQueue() {
    if (!this.metroRunning) return;
    const now = this.ctx.currentTime;
    while (this._queue.length && this._queue[0].time <= now) {
      const item = this._queue.shift();
      this._beatHandlers.forEach((fn) => fn(item));
    }
    this._raf = requestAnimationFrame(() => this._drainQueue());
  }

  _click(time, kind) {
    const ctx = this.ctx;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    const freq = kind === 'accent' ? 1760 : kind === 'beat' ? 1245 : 880;
    const peak = (kind === 'accent' ? 1 : kind === 'beat' ? 0.72 : 0.4) * this.metroVolume;
    osc.type = 'square';
    osc.frequency.setValueAtTime(freq, time);
    gain.gain.setValueAtTime(0.0001, time);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), time + 0.004);
    gain.gain.exponentialRampToValueAtTime(0.0001, time + 0.06);
    osc.connect(gain).connect(this.master);
    osc.start(time);
    osc.stop(time + 0.08);
  }

  /* ------------------------------------------------------------ drone */

  get droneRunning() { return !!this.droneNodes; }

  startDrone(midi = this.droneMidi) {
    const ctx = this.ensure();
    if (!ctx) return;
    this.droneMidi = midi;
    if (this.droneNodes) { this.setDronePitch(midi); return; }

    const out = ctx.createGain();
    out.gain.setValueAtTime(0.0001, ctx.currentTime);
    out.gain.exponentialRampToValueAtTime(this.droneVolume, ctx.currentTime + 0.35);

    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 3200;

    const base = midiToFreq(midi, this.a4);
    // A touch of harmonic content makes it easy to hear beats against the violin.
    const partials = [
      { ratio: 1, gain: 0.55, detune: 0 },
      { ratio: 1, gain: 0.22, detune: 4 },
      { ratio: 2, gain: 0.18, detune: 0 },
      { ratio: 3, gain: 0.09, detune: 0 },
      { ratio: 5, gain: 0.04, detune: 0 },
    ];
    const oscs = partials.map((p) => {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = base * p.ratio;
      osc.detune.value = p.detune;
      g.gain.value = p.gain;
      osc.connect(g).connect(filter);
      osc.start();
      return { osc, ratio: p.ratio };
    });
    filter.connect(out).connect(this.master);
    this.droneNodes = { oscs, out, filter };
  }

  setDronePitch(midi) {
    this.droneMidi = midi;
    if (!this.droneNodes) return;
    const base = midiToFreq(midi, this.a4);
    const t = this.ctx.currentTime;
    this.droneNodes.oscs.forEach(({ osc, ratio }) => {
      osc.frequency.cancelScheduledValues(t);
      osc.frequency.setTargetAtTime(base * ratio, t, 0.03);
    });
  }

  setDroneVolume(v) {
    this.droneVolume = Math.max(0, Math.min(1, v));
    if (this.droneNodes) {
      this.droneNodes.out.gain.setTargetAtTime(this.droneVolume, this.ctx.currentTime, 0.05);
    }
  }

  stopDrone() {
    if (!this.droneNodes) return;
    const { oscs, out } = this.droneNodes;
    const t = this.ctx.currentTime;
    out.gain.cancelScheduledValues(t);
    out.gain.setValueAtTime(Math.max(0.0001, out.gain.value), t);
    out.gain.exponentialRampToValueAtTime(0.0001, t + 0.25);
    oscs.forEach(({ osc }) => osc.stop(t + 0.3));
    this.droneNodes = null;
  }

  toggleDrone(midi) {
    if (this.droneRunning) { this.stopDrone(); return false; }
    this.startDrone(midi);
    return true;
  }

  /** A single reference pluck, used for quick pitch checks. */
  pluck(midi, duration = 1.2) {
    const ctx = this.ensure();
    if (!ctx) return;
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.value = midiToFreq(midi, this.a4);
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.4, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + duration);
    osc.connect(gain).connect(this.master);
    osc.start(t);
    osc.stop(t + duration + 0.05);
  }

  stopAll() {
    this.stopMetronome();
    this.stopDrone();
  }
}

export const audio = new AudioEngine();

/* ------------------------------------------------------------- tuner */

export const TUNER_MIN_HZ = 70;
export const TUNER_MAX_HZ = 3200;

/**
 * Autocorrelation pitch detection over a bounded lag range (cheap enough to
 * run every animation frame on a phone). Returns Hz, or -1 when the signal is
 * too quiet or has no clear period.
 */
export function autoCorrelate(buffer, sampleRate) {
  const n = buffer.length;
  let rms = 0;
  for (let i = 0; i < n; i += 1) rms += buffer[i] * buffer[i];
  rms = Math.sqrt(rms / n);
  if (rms < 0.008) return -1;

  const minLag = Math.max(2, Math.floor(sampleRate / TUNER_MAX_HZ));
  const maxLag = Math.min(n - 1, Math.ceil(sampleRate / TUNER_MIN_HZ));
  if (maxLag <= minLag) return -1;

  const norm = new Float32Array(maxLag + 2);
  let best = 0;
  for (let lag = minLag; lag <= maxLag; lag += 1) {
    let sum = 0;
    for (let i = 0, len = n - lag; i < len; i += 1) sum += buffer[i] * buffer[i + lag];
    // Dividing by the overlap length removes the taper that otherwise biases
    // the result toward short lags (i.e. an octave too high).
    const value = sum / (n - lag);
    norm[lag] = value;
    if (value > best) best = value;
  }
  if (best <= 0) return -1;

  // Take the *first* strong peak rather than the global maximum: that is the
  // fundamental, not one of its sub-octaves.
  let peak = -1;
  for (let lag = minLag + 1; lag < maxLag; lag += 1) {
    if (norm[lag] >= 0.9 * best && norm[lag] > norm[lag - 1] && norm[lag] >= norm[lag + 1]) { peak = lag; break; }
  }
  if (peak < 0) return -1;

  const y1 = norm[peak - 1];
  const y2 = norm[peak];
  const y3 = norm[peak + 1];
  const a = (y1 + y3 - 2 * y2) / 2;
  const b = (y3 - y1) / 2;
  const period = peak + (a ? -b / (2 * a) : 0);
  if (period <= 0) return -1;

  const freq = sampleRate / period;
  return freq >= TUNER_MIN_HZ && freq <= TUNER_MAX_HZ ? freq : -1;
}

export class Tuner {
  constructor() {
    this.stream = null;
    this.analyser = null;
    this.buffer = null;
    this.raf = null;
    this.running = false;
  }

  async start(onReading, a4 = 440) {
    if (this.running) return true;
    const ctx = audio.ensure();
    if (!ctx || !navigator.mediaDevices?.getUserMedia) throw new Error('此瀏覽器不支援麥克風輸入');
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    const source = ctx.createMediaStreamSource(this.stream);
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 2048;
    source.connect(this.analyser);
    this.buffer = new Float32Array(this.analyser.fftSize);
    this.running = true;

    let smoothed = null;
    const tick = () => {
      if (!this.running) return;
      this.analyser.getFloatTimeDomainData(this.buffer);
      const freq = autoCorrelate(this.buffer, ctx.sampleRate);
      if (freq > 0) {
        smoothed = smoothed === null ? freq : smoothed * 0.72 + freq * 0.28;
        onReading({ freq: smoothed, ...freqToNote(smoothed, a4) });
      } else {
        smoothed = null;
        onReading(null);
      }
      this.raf = requestAnimationFrame(tick);
    };
    tick();
    return true;
  }

  stop() {
    this.running = false;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = null;
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.analyser = null;
  }
}

/** Keep the screen on while practising (best effort; silently no-ops). */
export const wakeLock = {
  sentinel: null,
  async request() {
    try {
      if (!('wakeLock' in navigator)) return false;
      this.sentinel = await navigator.wakeLock.request('screen');
      this.sentinel.addEventListener?.('release', () => { this.sentinel = null; });
      return true;
    } catch { return false; }
  },
  release() {
    try { this.sentinel?.release(); } catch { /* ignore */ }
    this.sentinel = null;
  },
};
