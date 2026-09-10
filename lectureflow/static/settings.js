// Device-local configuration: which engines to use, and the keys they need.

const KEY = 'lectureflow.settings.v1';

export const DEFAULTS = {
  transcribe: 'auto',   // auto | backend | openai | browser
  text: 'auto',         // auto | backend | anthropic | openai | local
  openaiKey: '',
  anthropicKey: '',
  language: 'zh',
  openaiTranscribeModel: 'gpt-4o-mini-transcribe',
  openaiTextModel: 'gpt-4o-mini',
  anthropicModel: 'claude-opus-5',
};

export function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
    return { ...DEFAULTS, ...(saved && typeof saved === 'object' ? saved : {}) };
  } catch {
    return { ...DEFAULTS };
  }
}

export function save(settings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
    return true;
  } catch {
    return false; // private mode or quota; the app still runs for this session
  }
}

export function clearKeys(settings) {
  return { ...settings, openaiKey: '', anthropicKey: '' };
}

export function hasBrowserSpeech() {
  return typeof window !== 'undefined'
    && !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

/**
 * Decide which engine actually handles each job.
 *
 * `backend` is only in play when a LectureFlow server answered /api/status;
 * that is the case when the page is served by the Python app. Installed from
 * a static host there is no backend, so the choice is between the user's own
 * key and what the browser can do by itself.
 */
export function resolve(settings, backend) {
  const openai = !!settings.openaiKey.trim();
  const anthropic = !!settings.anthropicKey.trim();
  const speech = hasBrowserSpeech();

  let transcribe = settings.transcribe;
  if (transcribe === 'auto') {
    if (backend && backend.transcribe_ready) transcribe = 'backend';
    else if (openai) transcribe = 'openai';
    else if (speech) transcribe = 'browser';
    else transcribe = 'none';
  } else if (transcribe === 'backend' && !(backend && backend.transcribe_ready)) {
    transcribe = 'none';
  } else if (transcribe === 'openai' && !openai) {
    transcribe = 'none';
  } else if (transcribe === 'browser' && !speech) {
    transcribe = 'none';
  }

  let text = settings.text;
  if (text === 'auto') {
    if (backend && backend.text_ready) text = 'backend';
    else if (anthropic) text = 'anthropic';
    else if (openai) text = 'openai';
    else text = 'local';
  } else if (text === 'backend' && !(backend && backend.text_ready)) {
    text = 'local';
  } else if (text === 'anthropic' && !anthropic) {
    text = 'local';
  } else if (text === 'openai' && !openai) {
    text = 'local';
  }

  return { transcribe, text };
}

const TRANSCRIBE_LABELS = {
  backend: '本機伺服器', openai: 'OpenAI', browser: '瀏覽器辨識', none: '無法辨識',
};
const TEXT_LABELS = {
  backend: '本機伺服器', anthropic: 'Claude', openai: 'OpenAI', local: '本機規則',
};

export function describe(resolved) {
  return {
    transcribe: TRANSCRIBE_LABELS[resolved.transcribe] || resolved.transcribe,
    text: TEXT_LABELS[resolved.text] || resolved.text,
  };
}
