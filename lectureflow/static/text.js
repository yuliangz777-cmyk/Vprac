// Pure text helpers, shared by the app and the unit tests.

const MIN_OVERLAP = 4;
const MAX_OVERLAP = 120;

const SILENCE_ARTIFACT_SOURCES = [
  '字幕由amara.org社群提供', '字幕由amara.org社区提供', '謝謝觀看', '謝謝大家',
  '感謝觀看', '下次再見', '我們下次再見', '多謝收睇', '請不吝點贊訂閱轉發打賞支持明鏡與點點欄目',
  'thanksforwatching', 'thankyouforwatching', 'thankyou', 'subtitlesbyamara.org',
  'youtube', 'bye', 'byebye', 'pleasesubscribe',
];

export function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

export function formatClock(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return hours ? `${pad(hours)}:${pad(minutes)}:${pad(rest)}` : `${pad(minutes)}:${pad(rest)}`;
}

export function normalizeKey(text) {
  return String(text || '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[\s　-〿＀-￯!-\/:-@\[-`{-~]/g, '');
}

// Compare against the same normalised form the lookup key uses, so entries
// containing punctuation (amara.org) still match.
const SILENCE_ARTIFACTS = new Set(SILENCE_ARTIFACT_SOURCES.map(normalizeKey));

export function collapseRepeats(text) {
  let out = String(text || '').replace(/(.)\1{5,}/gu, (_, ch) => ch.repeat(2));
  for (let unit = 2; unit <= 24; unit++) {
    const pattern = new RegExp(`(.{${unit}}?)\\1{3,}`, 'gsu');
    out = out.replace(pattern, (_, group) => group.repeat(2));
  }
  return out;
}

export function looksLikeSilenceArtifact(text) {
  const key = normalizeKey(text);
  if (!key) return true;
  if (SILENCE_ARTIFACTS.has(key)) return true;
  return new Set(key).size === 1 && key.length <= 8;
}

export function cleanChunk(text) {
  let out = String(text || '').trim();
  if (!out) return '';
  out = collapseRepeats(out).replace(/[ \t]{2,}/g, ' ').trim();
  return looksLikeSilenceArtifact(out) ? '' : out;
}

function compact(text) {
  const chars = [];
  const positions = [];
  for (let i = 0; i < text.length; i++) {
    if (!/\s/.test(text[i])) {
      chars.push(text[i].toLowerCase());
      positions.push(i);
    }
  }
  return { text: chars.join(''), positions };
}

function isCjk(char) {
  const code = char.codePointAt(0);
  return (
    (code >= 0x3040 && code <= 0x30ff) ||
    (code >= 0x3400 && code <= 0x4dbf) ||
    (code >= 0x4e00 && code <= 0x9fff) ||
    (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0xff00 && code <= 0xff65)
  );
}

/** Append a new chunk, removing text duplicated by a deliberate audio overlap. */
export function joinTranscript(previous, addition) {
  let next = String(addition || '').trim();
  if (!next) return previous || '';
  const base = String(previous || '').replace(/\s+$/, '');
  if (!base) return next;

  const tail = compact(base.slice(-MAX_OVERLAP * 2));
  const head = compact(next);
  const limit = Math.min(MAX_OVERLAP, tail.text.length, head.text.length);
  for (let size = limit; size >= MIN_OVERLAP; size--) {
    if (tail.text.endsWith(head.text.slice(0, size))) {
      next = next.slice(head.positions[size - 1] + 1).replace(/^\s+/, '');
      break;
    }
  }
  if (!next) return base;

  const separator = !isCjk(base[base.length - 1]) && !isCjk(next[0]) ? ' ' : '';
  return base + separator + next;
}

function sentences(text) {
  return String(text || '')
    .replace(/\s+/g, ' ')
    .split(/[。！？!?\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Offline notes, used when no API key is configured. */
export function localSummary(text) {
  const list = sentences(text);
  const scored = list
    .map((sentence, index) => ({
      sentence,
      score:
        (sentence.length > 18 ? 2 : 0) +
        (sentence.length > 35 ? 1 : 0) +
        (/因此|所以|結論|重點|定義|代表|造成|導致|比較|差異/.test(sentence) ? 3 : 0) -
        index * 0.001,
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 6)
    .map((item) => item.sentence);

  const terms = [...new Set(
    text.match(/[A-Za-z][A-Za-z0-9-]{2,}|[一-鿿]{2,8}(?:理論|模型|方法|概念|指標|策略|成本|收益|市場|風險|定律|公式)/g) || []
  )].slice(0, 8);

  return {
    summary: scored,
    concepts: terms.map((term) => ({ term, explanation: '逐字稿中反覆出現的詞彙' })),
    exam_points: scored.slice(0, 3),
    open_questions: [],
    latest: list.slice(-2).join('。'),
  };
}

/** Offline answer: keyword overlap against the transcript. */
export function localAnswer(question, text) {
  const list = sentences(text);
  if (!list.length) return '目前逐字稿沒有足夠資訊。';
  const keys = [...new Set(normalizeKey(question).split(''))];
  const ranked = list
    .map((sentence) => ({
      sentence,
      score:
        keys.reduce((total, key) => total + (sentence.includes(key) ? 1 : 0), 0) +
        (/結論|重點/.test(question) && /所以|因此|結論|重點/.test(sentence) ? 4 : 0),
    }))
    .sort((a, b) => b.score - a.score);
  const hits = ranked.filter((item) => item.score > 0).slice(0, 3).map((item) => item.sentence);
  return (hits.length ? hits : list.slice(-2)).join('；');
}

export function notesToMarkdown(notes, transcript, meta = {}) {
  const lines = ['# LectureFlow 課堂筆記', ''];
  if (meta.date) lines.push(`日期：${meta.date}`);
  if (meta.duration) lines.push(`時長：${meta.duration}`);
  if (meta.date || meta.duration) lines.push('');
  if (notes.latest) lines.push('## 目前講到', '', notes.latest, '');
  const section = (title, items) => {
    if (!items || !items.length) return;
    lines.push(`## ${title}`, '');
    items.forEach((item) => lines.push(`- ${item}`));
    lines.push('');
  };
  section('重點摘要', notes.summary);
  if (notes.concepts && notes.concepts.length) {
    lines.push('## 重要名詞', '');
    notes.concepts.forEach((c) => lines.push(`- **${c.term}**：${c.explanation || ''}`));
    lines.push('');
  }
  section('考試重點', notes.exam_points);
  section('待追問', notes.open_questions);
  lines.push('## 完整逐字稿', '', transcript || '');
  return lines.join('\n');
}

/** Strip markdown fences and any prose wrapped around a JSON object. */
export function cleanJsonText(text) {
  let out = String(text || '').trim()
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/, '')
    .trim();
  const start = out.indexOf('{');
  const end = out.lastIndexOf('}');
  if (start !== -1 && end > start) out = out.slice(start, end + 1);
  return out.trim();
}

function asStringList(value) {
  if (typeof value === 'string') return value.trim() ? [value.trim()] : [];
  if (!Array.isArray(value)) return [];
  const out = [];
  for (const item of value) {
    if (typeof item === 'string' && item.trim()) out.push(item.trim());
    else if (item && typeof item === 'object') {
      const text = item.text || item.point || item.content;
      if (typeof text === 'string' && text.trim()) out.push(text.trim());
    }
  }
  return out;
}

/** Parse a model reply into the notes shape. Never throws.
 *  Mirrors lectureflow/textproc.py:parse_notes for the direct-API engines,
 *  which have no backend to do it for them. */
export function parseNotes(text) {
  const empty = { summary: [], concepts: [], exam_points: [], open_questions: [], latest: '' };
  let data;
  try {
    data = JSON.parse(cleanJsonText(text));
  } catch {
    const stripped = String(text || '').trim();
    return { ...empty, summary: stripped ? [stripped] : [] };
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) return empty;

  const concepts = [];
  if (Array.isArray(data.concepts)) {
    for (const item of data.concepts) {
      if (item && typeof item === 'object') {
        const term = String(item.term || '').trim();
        if (term) concepts.push({ term, explanation: String(item.explanation || '').trim() });
      } else if (typeof item === 'string' && item.trim()) {
        concepts.push({ term: item.trim(), explanation: '' });
      }
    }
  }

  return {
    summary: asStringList(data.summary),
    concepts,
    exam_points: asStringList(data.exam_points),
    open_questions: asStringList(data.open_questions),
    latest: typeof data.latest === 'string' ? data.latest.trim() : '',
  };
}
