// Pure audio helpers. No DOM, no Web Audio globals, so Node can unit test them.

export const TARGET_RATE = 16000;

/** Resample mono float audio. Integer ratios use a box filter as a cheap
 *  anti-alias stage; other ratios fall back to linear interpolation. */
export function resampleTo(input, inputRate, outputRate = TARGET_RATE) {
  if (!input.length || inputRate === outputRate) return input;

  const ratio = inputRate / outputRate;
  if (Number.isInteger(ratio) && ratio > 1) {
    const count = Math.floor(input.length / ratio);
    const out = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      let sum = 0;
      const base = i * ratio;
      for (let k = 0; k < ratio; k++) sum += input[base + k];
      out[i] = sum / ratio;
    }
    return out;
  }

  const count = Math.max(1, Math.round(input.length / ratio));
  const out = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const position = i * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, input.length - 1);
    const weight = position - left;
    out[i] = input[left] * (1 - weight) + input[right] * weight;
  }
  return out;
}

export function rms(frame) {
  if (!frame.length) return 0;
  let total = 0;
  for (let i = 0; i < frame.length; i++) total += frame[i] * frame[i];
  return Math.sqrt(total / frame.length);
}

export function dbfs(amplitude) {
  return 20 * Math.log10(Math.max(amplitude, 1e-9));
}

export function floatToPcm16(input) {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const clamped = Math.max(-1, Math.min(1, input[i]));
    out[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return out;
}

/** Minimal 16-bit mono RIFF/WAVE container. Every chunk is a complete file,
 *  which is what the transcription endpoint expects. */
export function encodeWav(samples, sampleRate = TARGET_RATE) {
  const pcm = floatToPcm16(samples);
  const buffer = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(buffer);
  const ascii = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  ascii(0, 'RIFF');
  view.setUint32(4, 36 + pcm.length * 2, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true); // PCM header size
  view.setUint16(20, 1, true); // format: PCM
  view.setUint16(22, 1, true); // channels
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, 'data');
  view.setUint32(40, pcm.length * 2, true);
  new Int16Array(buffer, 44).set(pcm);
  return buffer;
}

export const SEGMENTER_DEFAULTS = {
  sampleRate: TARGET_RATE,
  frameMs: 20,
  minSegmentMs: 1500,
  maxSegmentMs: 14000,
  silenceMs: 700,
  padMs: 300,
  overlapMs: 400,
  floorDb: -70,
  marginDb: 9,
  gateDb: -55,
  ceilingDb: -35,
  noiseWindowMs: 5000,
  noisePercentile: 0.1,
};

/**
 * Turns a continuous stream of audio into utterance-sized segments.
 *
 * It cuts on a pause rather than on a fixed clock, so a segment almost always
 * ends at a sentence boundary; that is what makes the transcript read like
 * prose instead of like sliced-up fragments. Audio with no speech in it is
 * dropped rather than uploaded, which both saves requests and avoids the
 * stock phrases Whisper-family models hallucinate over silence.
 */
export class Segmenter {
  constructor(options = {}) {
    this.options = { ...SEGMENTER_DEFAULTS, ...options };
    this.frameSize = Math.round((this.options.sampleRate * this.options.frameMs) / 1000);
    this.noiseDb = this.options.floorDb;
    this.level = this.options.floorDb;
    this._carry = new Float32Array(0);

    // Ring buffer of recent frame levels, used to estimate the noise floor.
    const window = Math.max(8, Math.round(this.options.noiseWindowMs / this.options.frameMs));
    this._levels = new Float32Array(window).fill(this.options.floorDb);
    this._levelCount = 0;
    this._levelCursor = 0;
    this._sinceEstimate = 0;
    this._reset();
  }

  _reset() {
    this.frames = [];
    this.hasSpeech = false;
    this.silenceRun = 0;
    this.lastSpeechIndex = -1;
  }

  get bufferedMs() {
    return this.frames.length * this.options.frameMs;
  }

  /** Low percentile of the recent level history: the room, minus the voice.
   *
   *  Speech is bursty - there is a dip between every syllable - so the tenth
   *  percentile of a five second window lands in those gaps rather than on the
   *  speech itself. That is what lets the threshold rise to meet a hissy room
   *  without the speaker's own voice walking it up until capture goes deaf.
   */
  _estimateNoise() {
    const { floorDb, ceilingDb, noisePercentile } = this.options;
    const used = Math.min(this._levelCount, this._levels.length);
    const sample = Array.from(this._levels.subarray(0, used)).sort((a, b) => a - b);
    const index = Math.min(sample.length - 1, Math.floor(sample.length * noisePercentile));
    this.noiseDb = Math.min(Math.max(sample[index], floorDb), ceilingDb);
  }

  _classify(frame) {
    const { marginDb, gateDb } = this.options;
    const level = dbfs(rms(frame));
    this.level = level;

    // Written in cursor order; the estimate only needs the multiset, not the
    // ordering, so the ring buffer can be read as-is.
    this._levels[this._levelCursor] = level;
    this._levelCursor = (this._levelCursor + 1) % this._levels.length;
    this._levelCount++;

    // The floor moves far slower than the frame rate; re-sorting every frame
    // would be pure waste inside an audio callback.
    if (this._sinceEstimate++ % 5 === 0) this._estimateNoise();

    return level > Math.max(this.noiseDb + marginDb, gateDb);
  }

  _flatten(frames) {
    const out = new Float32Array(frames.length * this.frameSize);
    frames.forEach((entry, index) => out.set(entry.data, index * this.frameSize));
    return out;
  }

  _recount() {
    this.hasSpeech = false;
    this.silenceRun = 0;
    this.lastSpeechIndex = -1;
    this.frames.forEach((entry, index) => {
      if (entry.speech) {
        this.hasSpeech = true;
        this.lastSpeechIndex = index;
        this.silenceRun = 0;
      } else {
        this.silenceRun++;
      }
    });
  }

  /** Feed arbitrary-length audio; returns any segments that just closed. */
  push(samples) {
    const { frameMs, minSegmentMs, maxSegmentMs, silenceMs, padMs, overlapMs } = this.options;
    const padFrames = Math.ceil(padMs / frameMs);
    const segments = [];

    let pending;
    if (this._carry.length) {
      pending = new Float32Array(this._carry.length + samples.length);
      pending.set(this._carry, 0);
      pending.set(samples, this._carry.length);
    } else {
      pending = samples;
    }

    let offset = 0;
    while (pending.length - offset >= this.frameSize) {
      const frame = pending.subarray(offset, offset + this.frameSize);
      offset += this.frameSize;

      const speech = this._classify(frame);
      this.frames.push({ data: Float32Array.from(frame), speech });
      if (speech) {
        this.hasSpeech = true;
        this.silenceRun = 0;
        this.lastSpeechIndex = this.frames.length - 1;
      } else {
        this.silenceRun++;
      }

      if (!this.hasSpeech) {
        // Nothing said yet: keep only enough lead-in that the first syllable
        // of whatever comes next is not clipped off.
        if (this.frames.length > padFrames) {
          this.frames.splice(0, this.frames.length - padFrames);
        }
        continue;
      }

      const closedByPause =
        this.silenceRun * frameMs >= silenceMs && this.bufferedMs >= minSegmentMs;

      if (closedByPause) {
        const cut = Math.min(this.frames.length, this.lastSpeechIndex + 1 + padFrames);
        segments.push({ samples: this._flatten(this.frames.slice(0, cut)), reason: 'pause' });
        const rest = this.frames.slice(cut);
        this.frames = rest.slice(Math.max(0, rest.length - padFrames));
        this._recount();
      } else if (this.bufferedMs >= maxSegmentMs) {
        // Someone is talking without pausing. Cut anyway, but carry a little
        // audio forward so the word straddling the cut survives in one half.
        const overlapFrames = Math.ceil(overlapMs / frameMs);
        segments.push({ samples: this._flatten(this.frames), reason: 'maxlen' });
        this.frames = this.frames.slice(Math.max(0, this.frames.length - overlapFrames));
        this._recount();
      }
    }

    this._carry = pending.subarray(offset).length
      ? Float32Array.from(pending.subarray(offset))
      : new Float32Array(0);
    return segments;
  }

  /** Emit whatever is buffered, for when the user presses stop. */
  flush() {
    if (!this.hasSpeech || this.bufferedMs < 400) {
      this._reset();
      return null;
    }
    const segment = { samples: this._flatten(this.frames), reason: 'flush' };
    this._reset();
    return segment;
  }
}
