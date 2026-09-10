import test from 'node:test';
import assert from 'node:assert/strict';

import {
  cleanChunk, collapseRepeats, formatClock, joinTranscript,
  localAnswer, localSummary, normalizeKey, notesToMarkdown,
} from '../lectureflow/static/text.js';
import {
  encodeWav, floatToPcm16, resampleTo, rms, dbfs, Segmenter, TARGET_RATE,
} from '../lectureflow/static/audio.js';

/* ------------------------------------------------------------------ text */

test('joinTranscript appends plain segments', () => {
  assert.equal(joinTranscript('第一句。', '第二句。'), '第一句。第二句。');
  assert.equal(joinTranscript('', '只有這句'), '只有這句');
  assert.equal(joinTranscript('已有內容', '  '), '已有內容');
});

test('joinTranscript removes the overlap a forced cut creates', () => {
  assert.equal(
    joinTranscript('今天我們談的是供給曲線', '供給曲線會往右移動'),
    '今天我們談的是供給曲線會往右移動',
  );
  assert.equal(joinTranscript('the supply curve', 'supply  curve shifts'), 'the supply curve shifts');
});

test('joinTranscript spaces latin words but not CJK', () => {
  assert.equal(joinTranscript('hello', 'there'), 'hello there');
  assert.equal(joinTranscript('你好', '世界'), '你好世界');
});

test('joinTranscript keeps a coincidental short overlap', () => {
  assert.equal(joinTranscript('結論是的', '的確如此'), '結論是的的確如此');
});

test('cleanChunk drops silence hallucinations but keeps speech', () => {
  for (const artifact of ['謝謝觀看', '字幕由Amara.org社群提供', 'Thanks for watching!', '。。。', '']) {
    assert.equal(cleanChunk(artifact), '', artifact);
  }
  assert.equal(cleanChunk('  這是真的內容。 '), '這是真的內容。');
});

test('collapseRepeats tames a looping model', () => {
  assert.equal(collapseRepeats('好的的的的的的的的'), '好的的');
  assert.equal(collapseRepeats('我們繼續我們繼續我們繼續我們繼續'), '我們繼續我們繼續');
});

test('normalizeKey strips punctuation and case', () => {
  assert.equal(normalizeKey('Amara.Org, 社群!'), 'amaraorg社群');
});

test('formatClock switches to hours past the hour mark', () => {
  assert.equal(formatClock(65), '01:05');
  assert.equal(formatClock(3725), '01:02:05');
  assert.equal(formatClock(-5), '00:00');
});

test('localSummary and localAnswer work without any API', () => {
  const text = '需求曲線向右下方傾斜。因此價格上升時需求量會下降。這是需求法則。';
  const notes = localSummary(text);
  assert.ok(notes.summary.length > 0);
  assert.ok(notes.latest.length > 0);
  assert.match(localAnswer('結論是什麼？', text), /因此|需求/);
  assert.equal(localAnswer('任何問題', ''), '目前逐字稿沒有足夠資訊。');
});

test('notesToMarkdown includes every populated section', () => {
  const markdown = notesToMarkdown(
    { summary: ['甲'], concepts: [{ term: '需求', explanation: '想買的量' }], exam_points: ['乙'], open_questions: [], latest: '在講需求' },
    '逐字稿內容',
    { date: '2026-01-01', duration: '10:00' },
  );
  assert.match(markdown, /## 重點摘要/);
  assert.match(markdown, /\*\*需求\*\*：想買的量/);
  assert.match(markdown, /## 考試重點/);
  assert.doesNotMatch(markdown, /## 待追問/);
  assert.match(markdown, /逐字稿內容/);
});

/* ----------------------------------------------------------------- audio */

test('resampleTo decimates an integer ratio and preserves duration', () => {
  const input = new Float32Array(48000).map((_, i) => Math.sin((2 * Math.PI * 440 * i) / 48000));
  const output = resampleTo(input, 48000, 16000);
  assert.equal(output.length, 16000);
  assert.ok(rms(output) > 0.5);
});

test('resampleTo handles a non-integer ratio', () => {
  const input = new Float32Array(44100).fill(0.5);
  const output = resampleTo(input, 44100, 16000);
  assert.equal(output.length, 16000);
  assert.ok(Math.abs(output[8000] - 0.5) < 1e-6);
});

test('resampleTo is a no-op at the target rate', () => {
  const input = new Float32Array([0.1, 0.2, 0.3]);
  assert.equal(resampleTo(input, 16000, 16000), input);
});

test('floatToPcm16 clamps out-of-range samples', () => {
  const pcm = floatToPcm16(new Float32Array([0, 1, -1, 2, -2]));
  assert.equal(pcm[0], 0);
  assert.equal(pcm[1], 32767);
  assert.equal(pcm[2], -32768);
  assert.equal(pcm[3], 32767);
  assert.equal(pcm[4], -32768);
});

test('encodeWav writes a complete standalone RIFF file', () => {
  const samples = new Float32Array(1600).fill(0.25);
  const buffer = encodeWav(samples, TARGET_RATE);
  const view = new DataView(buffer);
  const tag = (offset) => String.fromCharCode(
    view.getUint8(offset), view.getUint8(offset + 1), view.getUint8(offset + 2), view.getUint8(offset + 3),
  );

  assert.equal(buffer.byteLength, 44 + 1600 * 2);
  assert.equal(tag(0), 'RIFF');
  assert.equal(tag(8), 'WAVE');
  assert.equal(tag(12), 'fmt ');
  assert.equal(tag(36), 'data');
  assert.equal(view.getUint32(4, true), 36 + 1600 * 2);
  assert.equal(view.getUint16(20, true), 1, 'PCM format');
  assert.equal(view.getUint16(22, true), 1, 'mono');
  assert.equal(view.getUint32(24, true), TARGET_RATE);
  assert.equal(view.getUint32(28, true), TARGET_RATE * 2, 'byte rate');
  assert.equal(view.getUint16(34, true), 16, 'bit depth');
  assert.equal(view.getUint32(40, true), 1600 * 2);
});

test('dbfs never returns -Infinity for digital silence', () => {
  assert.ok(Number.isFinite(dbfs(0)));
  assert.ok(dbfs(0) < -150);
});

/* ------------------------------------------------------------- segmenter */

const seconds = (n) => Math.round(TARGET_RATE * n);

function silence(durationSeconds) {
  // Not perfectly digital: a real room always has a small noise floor.
  return new Float32Array(seconds(durationSeconds)).map(() => (Math.random() - 0.5) * 0.001);
}

function tone(durationSeconds, amplitude = 0.25) {
  return new Float32Array(seconds(durationSeconds))
    .map((_, i) => amplitude * Math.sin((2 * Math.PI * 220 * i) / TARGET_RATE));
}

function concat(...parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const part of parts) { out.set(part, offset); offset += part.length; }
  return out;
}

test('segmenter cuts an utterance at the following pause', () => {
  const segmenter = new Segmenter();
  const segments = segmenter.push(concat(silence(1), tone(2), silence(1.2)));

  assert.equal(segments.length, 1);
  assert.equal(segments[0].reason, 'pause');
  const durationMs = (segments[0].samples.length / TARGET_RATE) * 1000;
  // Two seconds of speech plus a short pad on each side.
  assert.ok(durationMs > 2100 && durationMs < 3000, `got ${durationMs}ms`);
});

test('segmenter never uploads pure silence and stays bounded', () => {
  const segmenter = new Segmenter();
  let emitted = 0;
  for (let i = 0; i < 30; i++) emitted += segmenter.push(silence(1)).length;

  assert.equal(emitted, 0);
  assert.ok(segmenter.bufferedMs <= 320, `buffer grew to ${segmenter.bufferedMs}ms`);
});

test('segmenter force-cuts a speaker who never pauses, with overlap', () => {
  const segmenter = new Segmenter();
  const segments = segmenter.push(tone(30));

  assert.ok(segments.length >= 2, `expected multiple segments, got ${segments.length}`);
  assert.ok(segments.every((s) => s.reason === 'maxlen'));
  for (const segment of segments) {
    const durationMs = (segment.samples.length / TARGET_RATE) * 1000;
    assert.ok(durationMs <= 14100, `segment ran to ${durationMs}ms`);
  }
  // The carried overlap means the pieces sum to more than the input duration.
  const total = segments.reduce((sum, s) => sum + s.samples.length, 0);
  assert.ok(total > seconds(13) * segments.length * 0.9);
});

test('segmenter accepts arbitrary block sizes across calls', () => {
  const segmenter = new Segmenter();
  const source = concat(silence(0.5), tone(2), silence(1.2));
  let segments = [];
  // 700 samples is deliberately not a multiple of the 320-sample frame.
  for (let offset = 0; offset < source.length; offset += 700) {
    segments = segments.concat(segmenter.push(source.subarray(offset, offset + 700)));
  }
  assert.equal(segments.length, 1);
  assert.equal(segments[0].reason, 'pause');
});

test('segmenter flush emits a trailing utterance and then clears', () => {
  const segmenter = new Segmenter();
  segmenter.push(concat(silence(0.4), tone(1.5)));
  const tail = segmenter.flush();

  assert.ok(tail, 'expected a flushed segment');
  assert.equal(tail.reason, 'flush');
  assert.equal(segmenter.flush(), null);
  assert.equal(segmenter.bufferedMs, 0);
});

test('segmenter flush drops a buffer with no speech in it', () => {
  const segmenter = new Segmenter();
  segmenter.push(silence(2));
  assert.equal(segmenter.flush(), null);
});

/** Speech-shaped audio: a carrier under a syllable envelope that dips to the
 *  room floor roughly four times a second, the way real speech does. */
function speech(durationSeconds, room = silence, amplitude = 0.25) {
  const base = room(durationSeconds);
  return base.map((value, i) => {
    const envelope = Math.max(0, Math.sin((2 * Math.PI * 4 * i) / TARGET_RATE));
    return value + amplitude * envelope * Math.sin((2 * Math.PI * 220 * i) / TARGET_RATE);
  });
}

test('speech does not walk the noise floor up over its own voice', () => {
  // Regression: the floor used to adapt on every frame, so a steady speaker
  // raised the threshold past their own level and capture went deaf.
  const segmenter = new Segmenter();
  segmenter.push(silence(1));
  segmenter.push(speech(20));

  assert.ok(segmenter.noiseDb < -50, `floor drifted to ${segmenter.noiseDb}`);

  // Speech twenty seconds in is still segmented normally.
  const segments = segmenter.push(concat(speech(2), silence(1.2)));
  assert.ok(segments.length >= 1);
  assert.ok(segments.some((s) => s.reason === 'pause'));
});

test('the floor ceiling keeps a loud speaker audible even against constant tone', () => {
  // A pure unmodulated tone is genuinely indistinguishable from steady noise
  // by an energy detector, so the floor does rise - but the ceiling stops it
  // short of the speaker, and the force-cut still produces segments.
  const segmenter = new Segmenter();
  const segments = segmenter.push(tone(30));

  assert.ok(segmenter.noiseDb <= -35 + 1e-6, `floor exceeded the ceiling: ${segmenter.noiseDb}`);
  assert.ok(segments.length >= 2, `expected force-cuts, got ${segments.length}`);
  assert.ok(segments.every((s) => s.reason === 'maxlen'));
});

test('segmenter adapts to a noisy room without gating out speech', () => {
  const hiss = (d) => new Float32Array(seconds(d)).map(() => (Math.random() - 0.5) * 0.02);
  const segmenter = new Segmenter();

  segmenter.push(hiss(2));
  assert.ok(segmenter.noiseDb > -60, `floor should rise to meet room noise, got ${segmenter.noiseDb}`);

  const segments = segmenter.push(concat(speech(2, hiss), hiss(1.5)));
  assert.equal(segments.length, 1);
  assert.equal(segments[0].reason, 'pause');
});

/* -------------------------------------------------------------- notes --- */

import { cleanJsonText, parseNotes } from '../lectureflow/static/text.js';
import * as config from '../lectureflow/static/settings.js';

test('parseNotes reads a clean object', () => {
  const notes = parseNotes(JSON.stringify({
    summary: ['一'], concepts: [{ term: '需求', explanation: '想買的量' }],
    exam_points: [], open_questions: ['為什麼'], latest: '在講需求',
  }));
  assert.deepEqual(notes.summary, ['一']);
  assert.deepEqual(notes.concepts, [{ term: '需求', explanation: '想買的量' }]);
  assert.equal(notes.latest, '在講需求');
});

test('parseNotes survives fences, prose and wrong shapes', () => {
  assert.deepEqual(parseNotes('好的：\n```json\n{"summary":["甲"]}\n```').summary, ['甲']);
  assert.deepEqual(parseNotes('模型只回了一段話').summary, ['模型只回了一段話']);

  const loose = parseNotes('{"summary":"單一字串","concepts":["名詞"],"latest":null}');
  assert.deepEqual(loose.summary, ['單一字串']);
  assert.deepEqual(loose.concepts, [{ term: '名詞', explanation: '' }]);
  assert.equal(loose.latest, '');

  const empty = parseNotes('[]');
  assert.deepEqual(empty.summary, []);
  assert.deepEqual(empty.concepts, []);
});

test('cleanJsonText trims fences and surrounding prose', () => {
  assert.equal(cleanJsonText('```json\n{"a":1}\n```'), '{"a":1}');
  assert.equal(cleanJsonText('前言 {"a":1} 後記'), '{"a":1}');
});

/* ------------------------------------------------------------ settings -- */

const BACKEND_READY = { transcribe_ready: true, text_ready: true };

test('auto prefers a backend when one answered', () => {
  assert.deepEqual(config.resolve(config.DEFAULTS, BACKEND_READY), {
    transcribe: 'backend', text: 'backend',
  });
});

test('auto falls back to a stored key when there is no backend', () => {
  assert.deepEqual(config.resolve({ ...config.DEFAULTS, openaiKey: 'sk-x' }, null), {
    transcribe: 'openai', text: 'openai',
  });
  // Claude cannot transcribe, so audio has nowhere to go without more setup.
  assert.deepEqual(config.resolve({ ...config.DEFAULTS, anthropicKey: 'sk-a' }, null), {
    transcribe: 'none', text: 'anthropic',
  });
});

test('auto degrades to offline rules with nothing configured', () => {
  // Node has no SpeechRecognition, standing in for a browser without it.
  assert.deepEqual(config.resolve(config.DEFAULTS, null), { transcribe: 'none', text: 'local' });
});

test('an explicit choice that cannot be honoured degrades instead of throwing', () => {
  const pinned = { ...config.DEFAULTS, transcribe: 'backend', text: 'anthropic' };
  assert.deepEqual(config.resolve(pinned, null), { transcribe: 'none', text: 'local' });

  const pinnedKeyless = { ...config.DEFAULTS, transcribe: 'openai', text: 'openai' };
  assert.deepEqual(config.resolve(pinnedKeyless, BACKEND_READY), {
    transcribe: 'none', text: 'local',
  });
});

test('an explicit choice wins over an available backend', () => {
  const pinned = { ...config.DEFAULTS, transcribe: 'openai', text: 'anthropic', openaiKey: 'sk-x', anthropicKey: 'sk-a' };
  assert.deepEqual(config.resolve(pinned, BACKEND_READY), {
    transcribe: 'openai', text: 'anthropic',
  });
});

test('clearKeys removes both keys and keeps the rest', () => {
  const cleared = config.clearKeys({ ...config.DEFAULTS, openaiKey: 'a', anthropicKey: 'b', language: 'ja' });
  assert.equal(cleared.openaiKey, '');
  assert.equal(cleared.anthropicKey, '');
  assert.equal(cleared.language, 'ja');
});

test('describe gives every resolved engine a human label', () => {
  for (const transcribe of ['backend', 'openai', 'browser', 'none']) {
    for (const text of ['backend', 'anthropic', 'openai', 'local']) {
      const labels = config.describe({ transcribe, text });
      assert.ok(labels.transcribe && labels.transcribe !== transcribe, transcribe);
      assert.ok(labels.text && labels.text !== text, text);
    }
  }
});
