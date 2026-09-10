import { Segmenter, encodeWav, resampleTo, TARGET_RATE } from './audio.js';
import { createTextEngine, createTranscribeEngine } from './engines.js';
import * as config from './settings.js';
import {
  cleanChunk, escapeHtml, formatClock, joinTranscript, localSummary, notesToMarkdown,
} from './text.js';

const $ = (id) => document.getElementById(id);
const el = {
  dot: $('dot'), state: $('state'), timer: $('timer'), settings: $('settings'),
  transcript: $('transcript'), chars: $('chars'), liveInfo: $('liveInfo'),
  level: $('level'), notes: $('notes'), noteStatus: $('noteStatus'),
  messages: $('messages'), question: $('question'), toast: $('toast'),
  start: $('start'), stop: $('stop'), clear: $('clear'),
  summarize: $('summarize'), export: $('export'), ask: $('ask'), backlog: $('backlog'),
  setup: $('setup'), setupSummary: $('setupSummary'), saveSetup: $('saveSetup'),
  clearKeys: $('clearKeys'), setTranscribe: $('setTranscribe'), setText: $('setText'),
  setOpenaiKey: $('setOpenaiKey'), setAnthropicKey: $('setAnthropicKey'),
  setLanguage: $('setLanguage'),
};

// Every URL is resolved against the page, so the same build works whether the
// Python app serves it at / or a static host serves it from a subdirectory.
const API_BASE = new URL('./api/', document.baseURI).href;
const WORKLET_URL = new URL('./capture-worklet.js', import.meta.url).href;

const STORAGE_KEY = 'lectureflow.session.v2';
const AUTO_SUMMARY_MS = 30000;
const AUTO_SUMMARY_CHARS = 320;

const state = {
  settings: config.load(),
  backend: null,
  resolved: { transcribe: 'none', text: 'local' },
  transcriber: null,
  text: null,
  listening: false,
  seconds: 0,
  timerId: null,
  notes: null,
  lastSummaryText: '',
  lastSummaryAt: 0,
  summarizing: false,
  startedAt: null,
};

const audio = { stream: null, context: null, node: null, sink: null, segmenter: null, watchdog: null };
const speech = { recognition: null };
const wake = { lock: null };
const uploads = { queue: [], inflight: 0, max: 2, seq: 0, nextEmit: 0, ready: new Map() };

/* ---------------------------------------------------------------- UI ---- */

function toast(message) {
  el.toast.textContent = message;
  el.toast.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.toast.classList.remove('show'), 3200);
}

const setInfo = (html) => { el.liveInfo.innerHTML = html; };

function setListening(active, info) {
  state.listening = active;
  el.dot.classList.toggle('live', active);
  el.state.textContent = active ? '正在聽講' : '已停止';
  el.start.disabled = active;
  el.stop.disabled = !active;
  if (info) setInfo(info);
  if (active && !state.timerId) {
    state.timerId = setInterval(() => {
      state.seconds++;
      el.timer.textContent = formatClock(state.seconds);
      if (state.seconds % 5 === 0) persist();
    }, 1000);
  }
  if (!active && state.timerId) {
    clearInterval(state.timerId);
    state.timerId = null;
    el.level.style.setProperty('--level', '0%');
  }
}

function updateCount() {
  el.chars.textContent = el.transcript.value.length;
  persist();
}

function updateBacklog() {
  const pending = uploads.queue.length + uploads.inflight;
  el.backlog.textContent = pending
    ? (pending > 3 ? `佇列 ${pending} 段（網路較慢）` : `處理中 ${pending} 段`)
    : '';
}

/* --------------------------------------------------------- persistence -- */

let persistTimer = null;
function persist() {
  clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        transcript: el.transcript.value, notes: state.notes,
        seconds: state.seconds, savedAt: Date.now(),
      }));
    } catch { /* private mode or quota: the session simply is not restorable */ }
  }, 400);
}

function restore() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (saved.transcript) el.transcript.value = saved.transcript;
    if (saved.notes) { state.notes = saved.notes; renderNotes(saved.notes); }
    if (saved.seconds) {
      state.seconds = saved.seconds;
      el.timer.textContent = formatClock(state.seconds);
    }
  } catch { /* ignore corrupt state */ }
  updateCount();
}

/* ------------------------------------------------------------- engines -- */

const BACKEND_CACHE = 'lectureflow.backend.v1';

/** Is there a LectureFlow server behind this page?
 *
 *  On a static install there is not, and the probe 404s. That answer is
 *  remembered for the session so a reload - including an offline one - does
 *  not repeat a request we already know will fail.
 */
async function probeBackend() {
  try {
    const cached = sessionStorage.getItem(BACKEND_CACHE);
    if (cached) return JSON.parse(cached);
  } catch { /* sessionStorage unavailable; just probe */ }

  if (navigator.onLine === false) return null;

  let status = null;
  try {
    const response = await fetch(`${API_BASE}status`, { headers: { Accept: 'application/json' } });
    if (response.ok) {
      const payload = await response.json();
      if (payload && typeof payload === 'object' && 'transcribe_ready' in payload) status = payload;
    }
  } catch { /* no server behind this page: a static install, which is expected */ }

  try { sessionStorage.setItem(BACKEND_CACHE, JSON.stringify(status)); } catch { /* ignore */ }
  return status;
}

function applyEngines() {
  state.resolved = config.resolve(state.settings, state.backend);
  const context = { settings: state.settings, apiBase: API_BASE };
  state.transcriber = createTranscribeEngine(state.resolved.transcribe, context);
  state.text = createTextEngine(state.resolved.text, context);

  const labels = config.describe(state.resolved);
  el.settings.textContent = `${labels.transcribe} · ${labels.text}`;
  el.settings.title = '點擊調整語音辨識與筆記來源';
  el.setupSummary.textContent = state.backend
    ? `已連上本機伺服器（${state.backend.transcribe_model}）。`
    : '沒有偵測到本機伺服器，將直接在這台裝置上運作。';
}

/* ------------------------------------------------------- upload queue --- */

async function transcribeWithRetry(job) {
  let delay = 600;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      return await state.transcriber.transcribe(job.buffer, el.transcript.value);
    } catch (error) {
      if (attempt === 2) throw error;
      await new Promise((resolve) => setTimeout(resolve, delay));
      delay *= 2.5;
    }
  }
  return '';
}

function drainReady() {
  while (uploads.ready.has(uploads.nextEmit)) {
    const text = uploads.ready.get(uploads.nextEmit);
    uploads.ready.delete(uploads.nextEmit);
    uploads.nextEmit++;
    if (text) appendTranscript(text);
  }
}

function pumpQueue() {
  while (uploads.inflight < uploads.max && uploads.queue.length) {
    const job = uploads.queue.shift();
    uploads.inflight++;
    updateBacklog();
    transcribeWithRetry(job)
      .then((text) => { uploads.ready.set(job.seq, text); })
      .catch((error) => {
        // Record an empty result so ordering advances and the rest of the
        // lecture keeps flowing; only the failed seconds are lost.
        uploads.ready.set(job.seq, '');
        setInfo(`轉錄失敗（${escapeHtml(error.message)}），下一段會繼續`);
      })
      .finally(() => {
        uploads.inflight--;
        drainReady();
        updateBacklog();
        pumpQueue();
      });
  }
  updateBacklog();
}

function enqueueSegment(samples) {
  uploads.queue.push({ seq: uploads.seq++, buffer: encodeWav(samples, TARGET_RATE) });
  pumpQueue();
}

/* ---------------------------------------------------------- transcript -- */

function appendTranscript(text) {
  const cleaned = cleanChunk(text);
  if (!cleaned) return;
  const atBottom =
    el.transcript.scrollHeight - el.transcript.scrollTop - el.transcript.clientHeight < 60;
  el.transcript.value = joinTranscript(el.transcript.value, cleaned);
  if (atBottom) el.transcript.scrollTop = el.transcript.scrollHeight;
  updateCount();
  if (state.listening) setInfo('即時轉錄中');
  maybeAutoSummarize();
}

/* --------------------------------------------------------------- audio -- */

async function requestWakeLock() {
  try {
    if ('wakeLock' in navigator) wake.lock = await navigator.wakeLock.request('screen');
  } catch { /* not fatal */ }
}

function releaseWakeLock() {
  try { wake.lock?.release(); } catch { /* ignore */ }
  wake.lock = null;
}

async function buildCaptureNode(context, source, onSamples) {
  if (context.audioWorklet) {
    try {
      await context.audioWorklet.addModule(WORKLET_URL);
      const node = new AudioWorkletNode(context, 'lectureflow-capture');
      node.port.onmessage = (event) => onSamples(event.data);
      source.connect(node);
      return node;
    } catch { /* fall through to the deprecated node */ }
  }
  const node = context.createScriptProcessor(4096, 1, 1);
  node.onaudioprocess = (event) => onSamples(Float32Array.from(event.inputBuffer.getChannelData(0)));
  source.connect(node);
  return node;
}

async function startCapture() {
  audio.stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });

  const Context = window.AudioContext || window.webkitAudioContext;
  try {
    audio.context = new Context({ sampleRate: TARGET_RATE });
  } catch {
    audio.context = new Context(); // Safari ignores the hint; we resample instead.
  }
  await audio.context.resume();

  const inputRate = audio.context.sampleRate;
  audio.segmenter = new Segmenter({ sampleRate: TARGET_RATE });
  const source = audio.context.createMediaStreamSource(audio.stream);

  audio.node = await buildCaptureNode(audio.context, source, (block) => {
    if (!state.listening) return;
    const samples = resampleTo(block, inputRate, TARGET_RATE);
    for (const segment of audio.segmenter.push(samples)) enqueueSegment(segment.samples);
    const level = Math.max(0, Math.min(1, (audio.segmenter.level + 60) / 60));
    el.level.style.setProperty('--level', `${Math.round(level * 100)}%`);
  });

  // Some browsers cull a graph whose tail is not connected to a destination.
  audio.sink = audio.context.createGain();
  audio.sink.gain.value = 0;
  audio.node.connect(audio.sink);
  audio.sink.connect(audio.context.destination);

  // A backgrounded tab can suspend the context; nudge it back awake.
  audio.watchdog = setInterval(() => {
    if (state.listening && audio.context?.state === 'suspended') {
      audio.context.resume().catch(() => {});
    }
  }, 3000);

  await requestWakeLock();
  setListening(true, '即時轉錄中');
}

function teardownCapture() {
  clearInterval(audio.watchdog);
  audio.watchdog = null;
  if (audio.segmenter) {
    const tail = audio.segmenter.flush();
    if (tail) enqueueSegment(tail.samples);
    audio.segmenter = null;
  }
  try { audio.node?.disconnect(); } catch { /* ignore */ }
  try { audio.sink?.disconnect(); } catch { /* ignore */ }
  if (audio.node && 'port' in audio.node) audio.node.port.onmessage = null;
  audio.node = null;
  audio.sink = null;
  audio.stream?.getTracks().forEach((track) => track.stop());
  audio.stream = null;
  audio.context?.close().catch(() => {});
  audio.context = null;
}

/* ----------------------------------------------- browser speech fallback */

function buildRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return null;
  const recognition = new Recognition();
  recognition.lang = state.settings.language === 'zh' ? 'zh-TW' : (state.settings.language || 'zh-TW');
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.onresult = (event) => {
    let final = '';
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const piece = event.results[i][0].transcript;
      if (event.results[i].isFinal) final += `${piece} `; else interim += piece;
    }
    if (final) appendTranscript(final);
    setInfo(interim ? `辨識中：${escapeHtml(interim)}` : '瀏覽器即時辨識中');
  };
  recognition.onend = () => {
    // Safari and Chrome both end the session periodically; restart it.
    if (state.listening) { try { recognition.start(); } catch { /* already running */ } }
  };
  recognition.onerror = (event) => {
    if (event.error === 'no-speech' || event.error === 'aborted') return;
    setInfo(`語音辨識錯誤：${escapeHtml(event.error)}`);
  };
  return recognition;
}

async function startBrowserSpeech() {
  speech.recognition = speech.recognition || buildRecognition();
  if (!speech.recognition) throw new Error('此瀏覽器不支援語音辨識，請在設定裡填入 API 金鑰。');
  await requestWakeLock();
  setListening(true, '瀏覽器即時辨識中');
  try { speech.recognition.start(); } catch { /* already running */ }
}

/* --------------------------------------------------------- controls ----- */

async function start() {
  if (state.listening) return;
  if (state.resolved.transcribe === 'none') {
    toast('請先在設定裡選擇語音辨識方式。');
    openSetup();
    return;
  }
  setInfo('正在取得麥克風…');
  try {
    if (state.resolved.transcribe === 'browser') await startBrowserSpeech();
    else await startCapture();
    state.startedAt = state.startedAt || new Date();
  } catch (error) {
    setListening(false, '無法啟動麥克風');
    toast(error.message || String(error));
  }
}

function stop() {
  if (!state.listening && !audio.stream) return;
  setListening(false, '已停止');
  teardownCapture();
  try { speech.recognition?.stop(); } catch { /* ignore */ }
  releaseWakeLock();
  persist();
}

/* ----------------------------------------------------------- notes ------ */

function renderNotes(notes) {
  const list = (title, items) => (items && items.length
    ? `<div class="note"><h3>${title}</h3><ul>${items.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul></div>`
    : '');

  let html = '';
  if (notes.latest) {
    html += `<div class="note"><h3>目前講到</h3><p class="latest">${escapeHtml(notes.latest)}</p></div>`;
  }
  html += list('重點摘要', notes.summary);
  if (notes.concepts?.length) {
    html += `<div class="note"><h3>重要名詞</h3>${notes.concepts
      .map((c) => `<p class="concept"><b>${escapeHtml(c.term)}</b> ${escapeHtml(c.explanation || '')}</p>`)
      .join('')}</div>`;
  }
  html += list('考試重點', notes.exam_points);
  html += list('待追問', notes.open_questions);
  el.notes.innerHTML = html || '<div class="empty">目前沒有可整理的內容。</div>';
}

function maybeAutoSummarize() {
  const text = el.transcript.value;
  const grown = text.length - state.lastSummaryText.length >= AUTO_SUMMARY_CHARS;
  const stale = Date.now() - state.lastSummaryAt >= AUTO_SUMMARY_MS;
  if (text.length > 120 && grown && stale) summarize(false);
}

async function summarize(explicit = true) {
  const text = el.transcript.value.trim();
  if (!text) { if (explicit) toast('目前沒有逐字稿'); return; }
  if (state.summarizing) { if (explicit) toast('正在整理中'); return; }

  state.summarizing = true;
  el.noteStatus.innerHTML = '<span class="spinner"></span> 正在整理';
  try {
    const notes = await state.text.summarize(text);
    state.notes = notes;
    state.lastSummaryText = text;
    renderNotes(notes);
    el.noteStatus.textContent = `已更新 ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    persist();
  } catch (error) {
    el.noteStatus.textContent = '整理失敗';
    if (explicit) toast(error.message);
  } finally {
    state.lastSummaryAt = Date.now();
    state.summarizing = false;
  }
}

/* -------------------------------------------------------------- q & a --- */

function addMessage(who, text, mine = false) {
  const node = document.createElement('div');
  node.className = `msg${mine ? ' user' : ''}`;
  node.innerHTML = `<div class="who">${escapeHtml(who)}</div><div class="bubble"></div>`;
  node.querySelector('.bubble').textContent = text;
  el.messages.appendChild(node);
  el.messages.scrollTop = el.messages.scrollHeight;
  return node.querySelector('.bubble');
}

async function ask() {
  const question = el.question.value.trim();
  const transcript = el.transcript.value.trim();
  if (!question) return;
  if (!transcript) { toast('目前沒有逐字稿'); return; }

  addMessage('你', question, true);
  el.question.value = '';
  const bubble = addMessage('回答', '…');

  try {
    const answer = await state.text.ask(transcript, question, (partial) => {
      bubble.textContent = partial;
      el.messages.scrollTop = el.messages.scrollHeight;
    });
    if (!answer.trim()) bubble.textContent = '（沒有取得回答）';
  } catch (error) {
    bubble.textContent = `回答失敗：${error.message}`;
  }
}

/* -------------------------------------------------------------- export -- */

function exportNotes() {
  const notes = state.notes || localSummary(el.transcript.value);
  const markdown = notesToMarkdown(notes, el.transcript.value, {
    date: (state.startedAt || new Date()).toLocaleString(),
    duration: formatClock(state.seconds),
  });
  const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `lectureflow-${new Date().toISOString().slice(0, 10)}.md`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function clearSession() {
  stop();
  if (!confirm('清空逐字稿與筆記？此動作無法復原。')) return;
  el.transcript.value = '';
  state.notes = null;
  state.lastSummaryText = '';
  state.lastSummaryAt = 0;
  state.seconds = 0;
  state.startedAt = null;
  el.timer.textContent = '00:00';
  el.notes.innerHTML = '<div class="empty">開始聽講後，系統會定期更新筆記。</div>';
  el.noteStatus.textContent = '尚未整理';
  uploads.queue.length = 0;
  uploads.ready.clear();
  uploads.seq = 0;
  uploads.nextEmit = 0;
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  updateCount();
}

/* -------------------------------------------------------------- setup --- */

function openSetup() {
  el.setTranscribe.value = state.settings.transcribe;
  el.setText.value = state.settings.text;
  el.setOpenaiKey.value = state.settings.openaiKey;
  el.setAnthropicKey.value = state.settings.anthropicKey;
  el.setLanguage.value = state.settings.language;
  if (typeof el.setup.showModal === 'function') el.setup.showModal();
  else el.setup.setAttribute('open', '');
}

function saveSetup() {
  state.settings = {
    ...state.settings,
    transcribe: el.setTranscribe.value,
    text: el.setText.value,
    openaiKey: el.setOpenaiKey.value.trim(),
    anthropicKey: el.setAnthropicKey.value.trim(),
    language: el.setLanguage.value.trim(),
  };
  const stored = config.save(state.settings);
  speech.recognition = null; // language may have changed
  applyEngines();
  const labels = config.describe(state.resolved);
  toast(stored ? `已套用：${labels.transcribe} · ${labels.text}` : '設定已套用，但無法寫入這台裝置的儲存空間。');
}

/* ---------------------------------------------------------------- wire -- */

el.start.onclick = start;
el.stop.onclick = stop;
el.clear.onclick = clearSession;
el.summarize.onclick = () => summarize(true);
el.export.onclick = exportNotes;
el.ask.onclick = ask;
el.settings.onclick = openSetup;
el.saveSetup.onclick = () => { saveSetup(); };
el.clearKeys.onclick = () => {
  el.setOpenaiKey.value = '';
  el.setAnthropicKey.value = '';
  state.settings = config.clearKeys(state.settings);
  config.save(state.settings);
  applyEngines();
  toast('已清除這台裝置上的金鑰。');
};

el.transcript.addEventListener('input', updateCount);
el.question.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); ask(); }
});
document.querySelectorAll('.chip').forEach((chip) => {
  chip.onclick = () => { el.question.value = chip.dataset.q; ask(); };
});
document.querySelectorAll('.tab').forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.panel').forEach((panel) => panel.classList.remove('active'));
    document.querySelector(`[data-panel="${tab.dataset.tab}"]`).classList.add('active');
  };
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && state.listening && !wake.lock) requestWakeLock();
});
window.addEventListener('pagehide', () => { persist(); stop(); });

async function init() {
  setListening(false, '等待開始');
  restore();
  applyEngines();
  state.backend = await probeBackend();
  applyEngines();

  if (state.resolved.transcribe === 'none') {
    setInfo('尚未設定語音辨識，點右上角設定');
  }

  if ('serviceWorker' in navigator) {
    try {
      await navigator.serviceWorker.register(new URL('./sw.js', import.meta.url), {
        scope: new URL('./', import.meta.url).pathname,
      });
    } catch { /* offline start-up is a bonus, not a requirement */ }
  }
}

init();
