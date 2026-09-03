// Static training content: skills, task pool, quest path, acceptance criteria,
// achievements. Pure data + pure functions so it can be unit-tested in Node.

export const SKILL_KEYS = ['intonation', 'bow', 'shifting', 'rhythm', 'tone', 'musicality', 'stage', 'stamina'];

export const SKILL_LABELS = {
  intonation: '音準',
  bow: '運弓',
  shifting: '換把',
  rhythm: '節奏',
  tone: '音色',
  musicality: '音樂性',
  stage: '舞台穩定',
  stamina: '耐力',
};

export const skillLabel = (key) => SKILL_LABELS[key] || key;

export const STATUS_LABELS = {
  planned: '計畫中',
  learning: '學習中',
  active: '主修中',
  polishing: '打磨中',
  competition: '可上場',
  rest: '休耕',
};

/**
 * The adaptive task pool. `tools` links a task to the built-in practice tools
 * so a quest can be started with the right tool already open.
 */
export const TASK_POOL = [
  {
    id: 'scale', cat: 'intonation', title: '三個八度音階＋琶音', mins: 25, xp: 25, slot: 'warmup',
    desc: '慢速、開 drone、每個換把點停住校正，音階與琶音各一次不看譜。',
    tools: ['drone', 'tuner'],
  },
  {
    id: 'double', cat: 'intonation', title: '雙音音準', mins: 20, xp: 25, slot: 'core',
    desc: '三度／六度／八度擇一，先無揉弦，聽泛音共鳴而不是看手指位置。',
    tools: ['drone'],
  },
  {
    id: 'openString', cat: 'bow', title: '空弦音色基礎', mins: 15, xp: 20, slot: 'warmup',
    desc: '全弓 8 拍：弓速、壓力、接觸點三者固定，錄一次確認起音沒有雜音。',
    tools: ['metronome', 'record'],
  },
  {
    id: 'bow', cat: 'bow', title: '運弓連貫', mins: 25, xp: 30, slot: 'core',
    desc: '以空弦重建弓速、弓段與換弓，再回原譜同一句比對。',
    tools: ['metronome'],
  },
  {
    id: 'detache', cat: 'bow', title: '分弓與擊弓', mins: 20, xp: 25, slot: 'core',
    desc: 'détaché → martelé → spiccato，每種 60、80、100 BPM 各一輪。',
    tools: ['metronome'],
  },
  {
    id: 'shift', cat: 'shifting', title: '換把控制', mins: 20, xp: 25, slot: 'core',
    desc: '主曲目選 4 個換把點，各做 10 次：先有中介音，再無聲移動。',
    tools: ['drone'],
  },
  {
    id: 'position', cat: 'shifting', title: '把位地圖', mins: 20, xp: 25, slot: 'core',
    desc: '同一段落用兩種指法演奏，決定比賽要用哪一種並寫進譜上。',
    tools: [],
  },
  {
    id: 'rhythm', cat: 'rhythm', title: '節奏固定', mins: 20, xp: 20, slot: 'core',
    desc: '困難段落搭節拍器，以 70% 速度連續完成三次不失誤才加速。',
    tools: ['metronome'],
  },
  {
    id: 'tempoLadder', cat: 'rhythm', title: '速度階梯', mins: 25, xp: 30, slot: 'core',
    desc: '從 60% 起每次 +4 BPM，失誤即退回兩階，記錄今天的天花板速度。',
    tools: ['metronome'],
  },
  {
    id: 'bach', cat: 'musicality', title: 'Bach 聲部訓練', mins: 25, xp: 30, slot: 'core',
    desc: '只處理和聲方向、發音、句尾與聲部分層，暫時不追求速度。',
    tools: ['record'],
  },
  {
    id: 'phrase', cat: 'musicality', title: '樂句設計', mins: 20, xp: 25, slot: 'core',
    desc: '在譜上標出高點與呼吸點，唱一次再拉一次，確認兩者一致。',
    tools: [],
  },
  {
    id: 'mainSlow', cat: 'intonation', title: '主曲目慢練', mins: 35, xp: 35, slot: 'core',
    desc: '選 2–3 個段落，60–70% 速度錄音一次，逐音檢查音準與換弓。',
    tools: ['metronome', 'record'],
  },
  {
    id: 'mainRun', cat: 'stamina', title: '主曲目串接', mins: 25, xp: 40, slot: 'boss',
    desc: '連續演奏 8–12 分鐘不中斷，記錄事故點的小節號。',
    tools: ['record'],
  },
  {
    id: 'cadenza', cat: 'shifting', title: 'Cadenza 專項', mins: 25, xp: 35, slot: 'core',
    desc: '最不穩的 8–16 小節：節奏變化練 4 種，再完整跑一次。',
    tools: ['metronome'],
  },
  {
    id: 'record', cat: 'stage', title: '不中斷錄影', mins: 20, xp: 45, slot: 'boss',
    desc: '錄影指定段落，不停、不重來，結束後只列 3 個問題。',
    tools: ['record'],
  },
  {
    id: 'tone', cat: 'tone', title: '音色實驗', mins: 15, xp: 20, slot: 'core',
    desc: '同一句用 3 種接觸點／弓速組合錄音，回放挑出最好的一種。',
    tools: ['record'],
  },
  {
    id: 'vibrato', cat: 'tone', title: '揉弦分級', mins: 15, xp: 20, slot: 'core',
    desc: '慢、中、快三種頻率各 8 拍，再放進樂句裡做強弱對應。',
    tools: ['metronome'],
  },
  {
    id: 'mental', cat: 'stage', title: '冷啟動模擬', mins: 15, xp: 30, slot: 'boss',
    desc: '放下琴 10 分鐘後，不熱身直接錄一次指定入口。',
    tools: ['record'],
  },
  {
    id: 'benchmark', cat: 'musicality', title: 'A/B Benchmark', mins: 15, xp: 25, slot: 'cooldown',
    desc: '與一個職業版本比對同一段，寫下 3 個具體差異（不是「比較好聽」）。',
    tools: [],
  },
  {
    id: 'memory', cat: 'stage', title: '背譜抽查', mins: 15, xp: 30, slot: 'cooldown',
    desc: '隨機從 3 個段落中間開始演奏，確認不靠慣性也能進得去。',
    tools: [],
  },
];

export const TASK_BY_ID = Object.fromEntries(TASK_POOL.map((t) => [t.id, t]));

export const TOOL_LABELS = { metronome: '節拍器', drone: '持續音', tuner: '調音器', record: '錄音' };

/** LV.1 – LV.7 competition path with machine-checkable gates. */
export const PHASES = [
  {
    lv: 'LV.1', name: '技術重建期',
    goal: '主曲目第一樂章可公開演出；系統性音準與右手漏洞顯著下降。',
    gate: { skills: 55, key: { intonation: 60, bow: 60 }, readiness: 55, streak: 3 },
  },
  {
    lv: 'LV.2', name: 'Pre-professional',
    goal: '建立 Bach、Mozart、主協奏曲、Paganini 與奏鳴曲的 audition repertoire。',
    gate: { skills: 62, key: { intonation: 68, bow: 68, shifting: 65 }, readiness: 65, streak: 7 },
  },
  {
    lv: 'LV.3', name: '職業訓練環境',
    goal: '固定競賽型老師、academy、masterclass 與國際 benchmark。',
    gate: { skills: 68, key: { intonation: 72, bow: 72, musicality: 70 }, readiness: 72, streak: 14 },
  },
  {
    lv: 'LV.4', name: 'Competition Build',
    goal: '依目標賽事提前 12–18 個月建立完整 competition repertoire。',
    gate: { skills: 72, key: { intonation: 76, bow: 75, stamina: 72 }, readiness: 78, streak: 21 },
  },
  {
    lv: 'LV.5', name: 'International Circuit',
    goal: '從 pre-screening 穩定推進到 semifinal。',
    gate: { skills: 76, key: { stage: 78, intonation: 80, stamina: 76 }, readiness: 84, streak: 30 },
  },
  {
    lv: 'LV.6', name: 'Final Round',
    goal: '建立 concerto with orchestra、projection、舞台壓力與排練效率。',
    gate: { skills: 82, key: { stage: 85, musicality: 84 }, readiness: 90, streak: 45 },
  },
  {
    lv: 'LV.7', name: 'Prize Winner',
    goal: '多次進決賽後進入真正的奪牌窗口。',
    gate: { skills: 88, key: { stage: 90, musicality: 90, intonation: 90 }, readiness: 95, streak: 60 },
  },
];

export const DAILY_ACCEPTANCE = [
  '至少一次完整錄音或錄影，不以練習當下的感覺判定完成。',
  '今日最嚴重的 3 個問題已定位到具體小節。',
  '至少一段慢練連續 3 次達到相同指法、弓法與節拍。',
  '沒有用反覆重來掩蓋進入點、換把或接弓不穩。',
  '結束前已寫下明日第一優先修正項目。',
];

export const WEEKLY_ACCEPTANCE = [
  '一週至少完成 2 次不中斷錄影。',
  '同一技術問題連續兩週未改善時，已改練法或帶去問老師。',
  '至少一次與職業演奏版本做 A/B benchmark。',
  '主曲目至少一段達到三次連續成功。',
  '已完成週回顧：3 項進步、3 項下週修正。',
];

/** Achievements are pure predicates over a computed stats object. */
export const ACHIEVEMENTS = [
  { id: 'first-day', icon: '🎻', name: '第一天', desc: '完成第一項每日任務。', test: (s) => s.totalTasksDone >= 1 },
  { id: 'streak-3', icon: '🔥', name: '三日連勝', desc: '連續 3 天完成當日任務。', test: (s) => s.bestStreak >= 3 },
  { id: 'streak-7', icon: '🔥', name: '一週不斷', desc: '連續 7 天完成當日任務。', test: (s) => s.bestStreak >= 7 },
  { id: 'streak-30', icon: '🏆', name: '一個月', desc: '連續 30 天完成當日任務。', test: (s) => s.bestStreak >= 30 },
  { id: 'hours-10', icon: '⏱️', name: '10 小時', desc: '累積練習 10 小時。', test: (s) => s.totalMinutes >= 600 },
  { id: 'hours-100', icon: '⏱️', name: '100 小時', desc: '累積練習 100 小時。', test: (s) => s.totalMinutes >= 6000 },
  { id: 'boss-1', icon: '👑', name: '首殺 Boss', desc: '完成第一次不中斷錄影驗收。', test: (s) => s.bossCount >= 1 },
  { id: 'boss-10', icon: '👑', name: '十次上場', desc: '完成 10 次 Boss 驗收。', test: (s) => s.bossCount >= 10 },
  { id: 'rec-5', icon: '🎙️', name: '錄音習慣', desc: '錄下 5 個 take。', test: (s) => s.recordingCount >= 5 },
  { id: 'review-4', icon: '📓', name: '四週回顧', desc: '完成 4 次週回顧。', test: (s) => s.weeklyReviewCount >= 4 },
  { id: 'ready-80', icon: '🎯', name: '可上場', desc: '任一曲目成熟度達 80%。', test: (s) => s.maxReadiness >= 80 },
  { id: 'all-70', icon: '📈', name: '全能 70', desc: '八項能力全部達到 70。', test: (s) => s.minSkill >= 70 },
  { id: 'comp-1', icon: '🏅', name: '上戰場', desc: '登錄第一場比賽紀錄。', test: (s) => s.competitionCount >= 1 },
  { id: 'perfect-day', icon: '✨', name: '完美一日', desc: '單日任務全清＋Boss 完成。', test: (s) => s.perfectDays >= 1 },
];

/* --------------------------------------------------------- pure logic */

/** XP required to *reach* a given level (cumulative). */
export function xpForLevel(level) {
  if (level <= 1) return 0;
  return Math.round(220 * Math.pow(level - 1, 1.45));
}

export function levelFromXp(xp) {
  let level = 1;
  while (level < 99 && xp >= xpForLevel(level + 1)) level += 1;
  return level;
}

export function levelProgress(xp) {
  const level = levelFromXp(xp);
  const base = xpForLevel(level);
  const next = xpForLevel(level + 1);
  return { level, base, next, into: xp - base, span: next - base, ratio: (xp - base) / (next - base) };
}

/**
 * Deterministic-ish adaptive daily plan.
 * Weights: weak skills first, then tasks recently left unfinished, then a
 * rotation penalty so the same quest does not appear every single day.
 * `rand` is injectable to keep the unit tests deterministic.
 */
export function buildDayPlan({ skills, recentDays = [], minutes = 210, mainWork = '主曲目', rand = Math.random }) {
  const ranked = Object.entries(skills).sort((a, b) => a[1] - b[1]);
  const weak = ranked.slice(0, 3).map(([k]) => k);
  const weakest = ranked[0]?.[0];

  const missed = new Set();
  const recentIds = new Map();
  recentDays.slice(-4).forEach((day, index, arr) => {
    const age = arr.length - index; // 1 = oldest of the window
    (day.tasks || []).forEach((t) => {
      if (!t.done) missed.add(t.id);
      recentIds.set(t.id, Math.max(recentIds.get(t.id) || 0, age));
    });
  });

  const scored = TASK_POOL.map((t) => {
    let score = rand() * 1.5;
    if (weak.includes(t.cat)) score += 4;
    if (t.cat === weakest) score += 1.5;
    // Unfinished work outranks everything: it comes back until it is done.
    if (missed.has(t.id)) score += 5;
    else if (recentIds.has(t.id)) score -= 1.2 * recentIds.get(t.id);
    if (t.slot === 'warmup') score += 1;
    if (t.slot === 'boss') score += 0.5;
    return { task: t, score };
  }).sort((a, b) => b.score - a.score);

  // Always open with a warm-up, always close with something that forces
  // performance conditions; fill the middle up to the available minutes.
  const budget = clampNumber(minutes, 45, 420);
  const chosen = [];
  let used = 0;
  const take = (entry) => {
    if (!entry || chosen.some((c) => c.id === entry.task.id)) return false;
    chosen.push(entry.task);
    used += entry.task.mins;
    return true;
  };

  take(scored.find((e) => e.task.slot === 'warmup'));
  for (const entry of scored) {
    if (chosen.length >= 7) break;
    if (used + entry.task.mins > budget - 20) continue;
    if (entry.task.slot === 'boss') continue;
    take(entry);
  }
  if (!chosen.some((t) => t.slot === 'boss')) take(scored.find((e) => e.task.slot === 'boss'));

  return chosen.map((t) => ({
    id: t.id,
    cat: t.cat,
    title: t.title,
    desc: t.desc.replace('主曲目', mainWork),
    mins: t.mins,
    xp: t.xp,
    tools: t.tools,
    done: false,
    spent: 0,
  }));
}

function clampNumber(n, min, max) {
  const v = Number(n);
  if (!Number.isFinite(v)) return min;
  return Math.max(min, Math.min(max, v));
}

/** How far a phase's gate is satisfied, 0..1, plus the failing requirements. */
export function phaseProgress(phase, { skills, repertoire, bestStreak }) {
  const values = Object.values(skills);
  const avg = values.reduce((a, b) => a + b, 0) / (values.length || 1);
  const minSkill = Math.min(...values);
  const maxReadiness = repertoire.length ? Math.max(...repertoire.map((r) => r.readiness || 0)) : 0;
  const checks = [
    { label: `八項能力平均 ${phase.gate.skills}`, ok: avg >= phase.gate.skills, ratio: avg / phase.gate.skills },
    { label: `最低能力不低於 ${phase.gate.skills - 10}`, ok: minSkill >= phase.gate.skills - 10, ratio: minSkill / (phase.gate.skills - 10) },
    { label: `主曲目成熟度 ${phase.gate.readiness}%`, ok: maxReadiness >= phase.gate.readiness, ratio: maxReadiness / phase.gate.readiness },
    { label: `最佳連勝 ${phase.gate.streak} 天`, ok: bestStreak >= phase.gate.streak, ratio: bestStreak / phase.gate.streak },
  ];
  for (const [key, need] of Object.entries(phase.gate.key)) {
    checks.push({
      label: `${skillLabel(key)} ${need}`,
      ok: (skills[key] || 0) >= need,
      ratio: (skills[key] || 0) / need,
    });
  }
  const ratio = checks.reduce((a, c) => a + Math.min(1, c.ratio || 0), 0) / checks.length;
  return { ratio, checks, complete: checks.every((c) => c.ok) };
}

/** Highest phase whose gate is fully met, plus the one currently in progress. */
export function currentPhaseIndex(stats) {
  let cleared = -1;
  PHASES.forEach((p, i) => { if (phaseProgress(p, stats).complete) cleared = i; });
  return Math.min(cleared + 1, PHASES.length - 1);
}
