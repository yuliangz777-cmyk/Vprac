// Pluggable back ends for the two jobs the app needs: turning audio into text,
// and turning text into notes and answers.
//
// The point of the split is that the installed app has to work with no laptop
// running. Served by the Python app it uses the backend; installed from a
// static host it uses the user's own key, or whatever the browser can do
// unaided.

import { NOTES_SYSTEM, ASK_SYSTEM, notesUserPrompt, askUserPrompt, clip } from './prompts.js';
import { localAnswer, localSummary, parseNotes } from './text.js';

const OPENAI_BASE = 'https://api.openai.com/v1';
const ANTHROPIC_BASE = 'https://api.anthropic.com/v1';

export class EngineError extends Error {}

async function describeFailure(response) {
  let detail = `HTTP ${response.status}`;
  try {
    const payload = await response.json();
    detail = payload?.error?.message || payload?.detail || payload?.error || detail;
  } catch { /* non-JSON body */ }
  if (response.status === 401) return `金鑰無效或已過期（${detail}）`;
  if (response.status === 429) return `已達速率上限，稍後會自動重試（${detail}）`;
  return String(detail);
}

/** Read an SSE body, handing each `data:` payload to `onEvent`. */
async function readEventStream(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop();
    for (const block of blocks) {
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const data = line.slice(5).trim();
        if (!data || data === '[DONE]') continue;
        let event;
        try { event = JSON.parse(data); } catch { continue; }
        if (onEvent(event) === false) return;
      }
    }
  }
}

/* ------------------------------------------------------------ transcribe -- */

class BackendTranscribe {
  constructor({ apiBase }) { this.apiBase = apiBase; this.id = 'backend'; }

  async transcribe(wav, hint) {
    const form = new FormData();
    form.append('file', new Blob([wav], { type: 'audio/wav' }), 'segment.wav');
    form.append('hint', hint.slice(-450));
    const response = await fetch(`${this.apiBase}transcribe`, { method: 'POST', body: form });
    if (!response.ok) throw new EngineError(await describeFailure(response));
    return (await response.json()).text || '';
  }
}

class OpenAITranscribe {
  constructor({ settings }) { this.settings = settings; this.id = 'openai'; }

  async transcribe(wav, hint) {
    const { openaiKey, openaiTranscribeModel, language } = this.settings;
    const form = new FormData();
    form.append('file', new Blob([wav], { type: 'audio/wav' }), 'segment.wav');
    form.append('model', openaiTranscribeModel);
    form.append('response_format', 'json');
    if (language) form.append('language', language);
    if (hint.trim()) form.append('prompt', hint.trim().slice(-450));

    const response = await fetch(`${OPENAI_BASE}/audio/transcriptions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${openaiKey.trim()}` },
      body: form,
    });
    if (!response.ok) throw new EngineError(await describeFailure(response));
    return ((await response.json()).text || '').trim();
  }
}

/* ------------------------------------------------------------------ text -- */

class BackendText {
  constructor({ apiBase }) { this.apiBase = apiBase; this.id = 'backend'; }

  async summarize(transcript) {
    const response = await fetch(`${this.apiBase}summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript }),
    });
    if (!response.ok) throw new EngineError(await describeFailure(response));
    return response.json();
  }

  async ask(transcript, question, onDelta) {
    const response = await fetch(`${this.apiBase}ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript, question }),
    });
    if (!response.ok || !response.body) throw new EngineError(await describeFailure(response));

    let answer = '';
    let failure = null;
    await readEventStream(response, (event) => {
      if (event.error) { failure = event.error; return false; }
      if (event.delta) { answer += event.delta; onDelta(answer); }
      return true;
    });
    if (failure) throw new EngineError(failure);
    return answer;
  }
}

class OpenAIText {
  constructor({ settings }) { this.settings = settings; this.id = 'openai'; }

  _headers() {
    return {
      Authorization: `Bearer ${this.settings.openaiKey.trim()}`,
      'Content-Type': 'application/json',
    };
  }

  _body(system, user, maxTokens, stream) {
    return JSON.stringify({
      model: this.settings.openaiTextModel,
      max_tokens: maxTokens,
      stream,
      messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
    });
  }

  async summarize(transcript) {
    const response = await fetch(`${OPENAI_BASE}/chat/completions`, {
      method: 'POST',
      headers: this._headers(),
      body: this._body(NOTES_SYSTEM, notesUserPrompt(transcript), 4000, false),
    });
    if (!response.ok) throw new EngineError(await describeFailure(response));
    const payload = await response.json();
    return parseNotes(payload.choices?.[0]?.message?.content || '');
  }

  async ask(transcript, question, onDelta) {
    const response = await fetch(`${OPENAI_BASE}/chat/completions`, {
      method: 'POST',
      headers: this._headers(),
      body: this._body(ASK_SYSTEM, askUserPrompt(transcript, question), 2000, true),
    });
    if (!response.ok || !response.body) throw new EngineError(await describeFailure(response));

    let answer = '';
    await readEventStream(response, (event) => {
      const piece = event.choices?.[0]?.delta?.content;
      if (piece) { answer += piece; onDelta(answer); }
      return true;
    });
    return answer;
  }
}

class AnthropicText {
  constructor({ settings }) {
    this.settings = settings;
    this.id = 'anthropic';
    this.supportsEffort = true;
  }

  _headers() {
    return {
      'x-api-key': this.settings.anthropicKey.trim(),
      'anthropic-version': '2023-06-01',
      // Calling the API straight from a page is off by default; the user opted
      // in by storing their key here, so say so explicitly.
      'anthropic-dangerous-direct-browser-access': 'true',
      'Content-Type': 'application/json',
    };
  }

  _body(system, user, maxTokens, stream) {
    const body = {
      model: this.settings.anthropicModel,
      max_tokens: maxTokens,
      system,
      messages: [{ role: 'user', content: user }],
      stream,
    };
    // Lecture notes are a simple, latency-sensitive job; low effort answers
    // sooner. Dropped automatically if this account's API does not take it.
    if (this.supportsEffort) body.output_config = { effort: 'low' };
    return JSON.stringify(body);
  }

  async _post(system, user, maxTokens, stream) {
    for (;;) {
      const response = await fetch(`${ANTHROPIC_BASE}/messages`, {
        method: 'POST', headers: this._headers(), body: this._body(system, user, maxTokens, stream),
      });
      if (response.ok) return response;
      if (response.status === 400 && this.supportsEffort) {
        this.supportsEffort = false;
        continue;
      }
      throw new EngineError(await describeFailure(response));
    }
  }

  async summarize(transcript) {
    const response = await this._post(NOTES_SYSTEM, notesUserPrompt(transcript), 8000, false);
    const payload = await response.json();
    if (payload.stop_reason === 'refusal') throw new EngineError('模型拒絕回覆此請求。');
    const text = (payload.content || [])
      .filter((block) => block.type === 'text').map((block) => block.text).join('\n');
    return parseNotes(text);
  }

  async ask(transcript, question, onDelta) {
    const response = await this._post(ASK_SYSTEM, askUserPrompt(transcript, question), 4000, true);
    if (!response.body) throw new EngineError('串流回應為空。');

    let answer = '';
    await readEventStream(response, (event) => {
      if (event.type === 'content_block_delta' && event.delta?.type === 'text_delta') {
        answer += event.delta.text;
        onDelta(answer);
      }
      return true;
    });
    return answer;
  }
}

class LocalText {
  constructor() { this.id = 'local'; }

  async summarize(transcript) { return localSummary(clip(transcript)); }

  async ask(transcript, question, onDelta) {
    const answer = localAnswer(question, clip(transcript));
    onDelta(answer);
    return answer;
  }
}

/* --------------------------------------------------------------- factory -- */

export function createTranscribeEngine(kind, context) {
  if (kind === 'backend') return new BackendTranscribe(context);
  if (kind === 'openai') return new OpenAITranscribe(context);
  return null; // 'browser' is handled by SpeechRecognition, 'none' by nothing
}

export function createTextEngine(kind, context) {
  if (kind === 'backend') return new BackendText(context);
  if (kind === 'openai') return new OpenAIText(context);
  if (kind === 'anthropic') return new AnthropicText(context);
  return new LocalText();
}
