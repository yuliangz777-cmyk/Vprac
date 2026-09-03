// Microphone take recorder built on MediaRecorder, with a live level meter.

import { audio } from './audio.js';
import { uid, dateKey } from './util.js';
import { recordingsDB } from './db.js';

const CANDIDATE_TYPES = [
  'audio/mp4',            // Safari / iOS
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
];

export function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return '';
  for (const type of CANDIDATE_TYPES) {
    if (MediaRecorder.isTypeSupported?.(type)) return type;
  }
  return '';
}

export const recorderSupported = () => typeof MediaRecorder !== 'undefined'
  && !!navigator.mediaDevices?.getUserMedia;

export class TakeRecorder {
  constructor() {
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
    this.startedAt = 0;
    this.raf = null;
    this.state = 'idle';
  }

  get elapsed() {
    return this.startedAt ? (Date.now() - this.startedAt) / 1000 : 0;
  }

  async start(onLevel) {
    if (!recorderSupported()) throw new Error('此瀏覽器不支援錄音功能');
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    const mimeType = pickMimeType();
    this.recorder = new MediaRecorder(this.stream, mimeType ? { mimeType } : undefined);
    this.chunks = [];
    this.recorder.ondataavailable = (e) => { if (e.data && e.data.size) this.chunks.push(e.data); };
    this.recorder.start(500);
    this.startedAt = Date.now();
    this.state = 'recording';

    if (onLevel) this._meter(onLevel);
    return true;
  }

  _meter(onLevel) {
    const ctx = audio.ensure();
    if (!ctx) return;
    const source = ctx.createMediaStreamSource(this.stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const tick = () => {
      if (this.state !== 'recording') return;
      analyser.getFloatTimeDomainData(buf);
      let peak = 0;
      for (let i = 0; i < buf.length; i += 1) peak = Math.max(peak, Math.abs(buf[i]));
      onLevel(peak, this.elapsed);
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  /** Stop and resolve with the finished blob. */
  stop() {
    return new Promise((resolve) => {
      if (!this.recorder || this.state !== 'recording') { resolve(null); return; }
      const seconds = this.elapsed;
      const mime = this.recorder.mimeType || 'audio/mp4';
      this.recorder.onstop = () => {
        const blob = new Blob(this.chunks, { type: mime });
        this._cleanup();
        resolve({ blob, mime, seconds });
      };
      this.state = 'stopping';
      this.recorder.stop();
    });
  }

  cancel() {
    if (this.recorder && this.state === 'recording') {
      this.recorder.onstop = () => this._cleanup();
      this.state = 'stopping';
      this.recorder.stop();
    } else {
      this._cleanup();
    }
  }

  _cleanup() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = null;
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.recorder = null;
    this.state = 'idle';
    this.startedAt = 0;
  }
}

/** Persist a finished take and return the stored record. */
export async function saveTake({ blob, mime, seconds }, meta = {}) {
  const record = {
    id: uid('rec'),
    dayKey: meta.dayKey || dateKey(),
    title: meta.title || `Take ${new Date().toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })}`,
    taskId: meta.taskId || '',
    note: meta.note || '',
    rating: meta.rating || 0,
    mime,
    seconds: Math.round(seconds),
    size: blob.size,
    createdAt: new Date().toISOString(),
    blob,
  };
  await recordingsDB.add(record);
  return record;
}
