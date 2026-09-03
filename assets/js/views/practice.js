// Practice tools: metronome (with tempo ladder), drone, chromatic tuner and a
// free practice timer.

import { audio, Tuner, midiToFreq, OPEN_STRINGS } from '../audio.js';
import { setSetting } from '../state.js';
import { session } from '../session.js';
import { pageHead, sectionTitle } from '../components.js';
import { $, $$, esc, clamp, formatClock, toast } from '../util.js';

const TABS = [
  { id: 'metronome', label: '節拍器', icon: '🥁' },
  { id: 'drone', label: '持續音', icon: '🎵' },
  { id: 'tuner', label: '調音器', icon: '📈' },
  { id: 'timer', label: '計時器', icon: '⏱️' },
];

const NOTE_NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'];

const TEMPO_MARKS = [
  { bpm: 48, name: 'Largo' }, { bpm: 60, name: 'Adagio' }, { bpm: 76, name: 'Andante' },
  { bpm: 96, name: 'Moderato' }, { bpm: 120, name: 'Allegro' }, { bpm: 152, name: 'Presto' },
];

// Kept at module scope so the settings survive tab switches within a session.
const ladder = { on: false, target: 132, step: 4, bars: 2, barCount: 0 };
let tapTimes = [];
let tuner = null;

export const practiceView = {
  id: 'practice',
  label: '練習',
  title: '練習工具',
  icon: '🎼',
  primary: true,

  mount(root, params = []) {
    let tab = TABS.some((t) => t.id === params[0]) ? params[0] : 'metronome';
    let offBeat = null;
    let timerInterval = null;
    let countdown = null; // { endsAt, total }

    const shell = () => {
      root.innerHTML = `
        ${pageHead('練習工具', '節拍器、持續音、調音器與計時器都在離線可用。')}
        <div class="segmented" role="tablist">
          ${TABS.map((t) => `<button role="tab" class="segmented__btn ${t.id === tab ? 'is-on' : ''}" data-tab="${t.id}">${t.icon} ${t.label}</button>`).join('')}
        </div>
        <div id="toolPane"></div>`;
      $$('[data-tab]', root).forEach((btn) => btn.addEventListener('click', () => {
        tab = btn.dataset.tab;
        if (tab !== 'tuner' && tuner) { tuner.stop(); tuner = null; }
        shell();
      }));
      renderPane();
    };

    const pane = () => $('#toolPane', root);

    function renderPane() {
      if (tab === 'metronome') renderMetronome();
      if (tab === 'drone') renderDrone();
      if (tab === 'tuner') renderTuner();
      if (tab === 'timer') renderTimer();
    }

    /* ------------------------------------------------------ metronome */

    function renderMetronome() {
      const beats = audio.beats;
      pane().innerHTML = `
        <section class="card tool">
          <div class="tempo">
            <button class="round-btn" data-bpm="-1">−</button>
            <div class="tempo__value"><strong data-bpm-label>${audio.bpm}</strong><span>BPM</span></div>
            <button class="round-btn" data-bpm="1">+</button>
          </div>
          <input class="slider" type="range" min="30" max="240" value="${audio.bpm}" data-bpm-range>
          <div class="row row--wrap tempo__marks">
            ${TEMPO_MARKS.map((m) => `<button class="chip" data-set-bpm="${m.bpm}">${m.name} ${m.bpm}</button>`).join('')}
          </div>
          <div class="beats" data-beats>
            ${Array.from({ length: beats }, (_, i) => `<span class="beat ${i === 0 ? 'beat--accent' : ''}" data-beat="${i}"></span>`).join('')}
          </div>
          <div class="row row--center" style="margin:14px 0 4px">
            <button class="btn btn--big ${audio.metroRunning ? 'btn--danger' : 'btn--primary'}" data-metro-toggle>${audio.metroRunning ? '■ 停止' : '▶︎ 開始'}</button>
            <button class="btn btn--ghost btn--big" data-tap>Tap</button>
          </div>
          <div class="grid-2">
            <label class="field"><span class="field__label">每小節拍數</span>
              <select class="input" data-beats-select>${[2, 3, 4, 5, 6, 7, 8].map((n) => `<option value="${n}" ${n === beats ? 'selected' : ''}>${n} 拍</option>`).join('')}</select>
            </label>
            <label class="field"><span class="field__label">細分</span>
              <select class="input" data-sub-select>
                ${[[1, '四分'], [2, '八分'], [3, '三連音'], [4, '十六分']].map(([v, l]) => `<option value="${v}" ${v === audio.subdivision ? 'selected' : ''}>${l}</option>`).join('')}
              </select>
            </label>
          </div>
          <label class="switch"><input type="checkbox" data-accent ${audio.accent ? 'checked' : ''}><span>強調第一拍</span></label>
          <label class="field"><span class="field__label">音量</span>
            <input class="slider" type="range" min="0" max="100" value="${Math.round(audio.metroVolume * 100)}" data-metro-vol>
          </label>
        </section>

        ${sectionTitle('速度階梯')}
        <section class="card tool">
          <p class="muted small">每 N 小節自動加速，用來把慢練速度推到目標速度。失誤就按停止，回到上一階再練。</p>
          <div class="grid-3">
            <label class="field"><span class="field__label">目標 BPM</span><input class="input" type="number" min="40" max="240" value="${ladder.target}" data-ladder-target></label>
            <label class="field"><span class="field__label">每階 +BPM</span><input class="input" type="number" min="1" max="20" value="${ladder.step}" data-ladder-step></label>
            <label class="field"><span class="field__label">每 N 小節</span><input class="input" type="number" min="1" max="16" value="${ladder.bars}" data-ladder-bars></label>
          </div>
          <label class="switch"><input type="checkbox" data-ladder-on ${ladder.on ? 'checked' : ''}><span>啟用速度階梯</span></label>
          <p class="muted small" data-ladder-status>${ladder.on ? `目前 ${audio.bpm} → 目標 ${ladder.target} BPM` : '未啟用'}</p>
        </section>`;

      const bpmLabel = $('[data-bpm-label]', root);
      const bpmRange = $('[data-bpm-range]', root);
      const syncBpm = (value) => {
        audio.setTempo(value);
        bpmLabel.textContent = audio.bpm;
        bpmRange.value = audio.bpm;
      };

      $$('[data-bpm]', root).forEach((b) => b.addEventListener('click', () => syncBpm(audio.bpm + Number(b.dataset.bpm))));
      bpmRange.addEventListener('input', () => syncBpm(Number(bpmRange.value)));
      $$('[data-set-bpm]', root).forEach((b) => b.addEventListener('click', () => syncBpm(Number(b.dataset.setBpm))));

      $('[data-metro-toggle]', root).addEventListener('click', (e) => {
        ladder.barCount = 0;
        const running = audio.toggleMetronome();
        e.currentTarget.textContent = running ? '■ 停止' : '▶︎ 開始';
        e.currentTarget.classList.toggle('btn--danger', running);
        e.currentTarget.classList.toggle('btn--primary', !running);
        window.dispatchEvent(new CustomEvent('vq:audio-changed'));
      });

      $('[data-tap]', root).addEventListener('click', () => {
        const now = Date.now();
        tapTimes = tapTimes.filter((t) => now - t < 2500);
        tapTimes.push(now);
        if (tapTimes.length >= 2) {
          const gaps = tapTimes.slice(1).map((t, i) => t - tapTimes[i]);
          const avg = gaps.reduce((a, b) => a + b, 0) / gaps.length;
          syncBpm(Math.round(60000 / avg));
        }
      });

      $('[data-beats-select]', root).addEventListener('change', (e) => {
        audio.beats = Number(e.target.value);
        renderMetronome();
      });
      $('[data-sub-select]', root).addEventListener('change', (e) => { audio.subdivision = Number(e.target.value); });
      $('[data-accent]', root).addEventListener('change', (e) => { audio.accent = e.target.checked; });
      $('[data-metro-vol]', root).addEventListener('input', (e) => { audio.metroVolume = Number(e.target.value) / 100; });

      $('[data-ladder-on]', root).addEventListener('change', (e) => { ladder.on = e.target.checked; ladder.barCount = 0; updateLadderStatus(); });
      $('[data-ladder-target]', root).addEventListener('change', (e) => { ladder.target = clamp(Number(e.target.value) || 120, 40, 240); updateLadderStatus(); });
      $('[data-ladder-step]', root).addEventListener('change', (e) => { ladder.step = clamp(Number(e.target.value) || 4, 1, 20); });
      $('[data-ladder-bars]', root).addEventListener('change', (e) => { ladder.bars = clamp(Number(e.target.value) || 2, 1, 16); });

      if (offBeat) offBeat();
      offBeat = audio.onBeat(({ beat, sub }) => {
        const dots = $$('[data-beat]', root);
        dots.forEach((d, i) => d.classList.toggle('is-on', i === beat && beat >= 0));
        if (sub !== 0 || beat !== 0) return;
        if (!ladder.on) return;
        ladder.barCount += 1;
        if (ladder.barCount >= ladder.bars) {
          ladder.barCount = 0;
          if (audio.bpm < ladder.target) {
            syncBpm(Math.min(ladder.target, audio.bpm + ladder.step));
            updateLadderStatus();
            if (audio.bpm >= ladder.target) toast(`已達目標速度 ${ladder.target} BPM`, 'good');
          }
        }
      });

      function updateLadderStatus() {
        const el = $('[data-ladder-status]', root);
        if (el) el.textContent = ladder.on ? `目前 ${audio.bpm} → 目標 ${ladder.target} BPM` : '未啟用';
      }
    }

    /* ---------------------------------------------------------- drone */

    function renderDrone() {
      const midi = audio.droneMidi;
      pane().innerHTML = `
        <section class="card tool">
          <div class="drone__now">
            <strong>${esc(NOTE_NAMES[((midi % 12) + 12) % 12])}${Math.floor(midi / 12) - 1}</strong>
            <span>${midiToFreq(midi, audio.a4).toFixed(1)} Hz · A4 = ${audio.a4} Hz</span>
          </div>
          <div class="row row--center" style="margin:6px 0 14px">
            <button class="btn btn--big ${audio.droneRunning ? 'btn--danger' : 'btn--primary'}" data-drone-toggle>${audio.droneRunning ? '■ 停止' : '▶︎ 播放'}</button>
          </div>
          <p class="field__label">空弦</p>
          <div class="row row--wrap">
            ${OPEN_STRINGS.map((s) => `<button class="chip chip--lg ${s.midi === midi ? 'is-on' : ''}" data-note="${s.midi}">${s.name}</button>`).join('')}
          </div>
          <p class="field__label" style="margin-top:14px">半音</p>
          <div class="keys">
            ${NOTE_NAMES.map((n, i) => {
              const m = 57 + i; // A3 upwards
              return `<button class="key ${n.includes('♯') ? 'key--black' : ''} ${m === midi ? 'is-on' : ''}" data-note="${m}">${n}</button>`;
            }).join('')}
          </div>
          <div class="grid-2" style="margin-top:14px">
            <label class="field"><span class="field__label">八度</span>
              <select class="input" data-octave>${[2, 3, 4, 5].map((o) => `<option value="${o}" ${Math.floor(midi / 12) - 1 === o ? 'selected' : ''}>${o}</option>`).join('')}</select>
            </label>
            <label class="field"><span class="field__label">音量</span>
              <input class="slider" type="range" min="0" max="100" value="${Math.round(audio.droneVolume * 100)}" data-drone-vol>
            </label>
          </div>
          <p class="muted small" style="margin-top:10px">用法：拉音階時開持續音，聽的是「有沒有共鳴」，不是「看起來對不對」。</p>
        </section>`;

      $('[data-drone-toggle]', root).addEventListener('click', () => {
        audio.toggleDrone(audio.droneMidi);
        window.dispatchEvent(new CustomEvent('vq:audio-changed'));
        renderDrone();
      });
      $$('[data-note]', root).forEach((b) => b.addEventListener('click', () => {
        const m = Number(b.dataset.note);
        audio.droneMidi = m;
        if (audio.droneRunning) audio.setDronePitch(m); else audio.startDrone(m);
        window.dispatchEvent(new CustomEvent('vq:audio-changed'));
        renderDrone();
      }));
      $('[data-octave]', root).addEventListener('change', (e) => {
        const octave = Number(e.target.value);
        const pitchClass = ((audio.droneMidi % 12) + 12) % 12;
        const m = (octave + 1) * 12 + pitchClass;
        audio.droneMidi = m;
        if (audio.droneRunning) audio.setDronePitch(m);
        renderDrone();
      });
      $('[data-drone-vol]', root).addEventListener('input', (e) => audio.setDroneVolume(Number(e.target.value) / 100));
    }

    /* ---------------------------------------------------------- tuner */

    function renderTuner() {
      pane().innerHTML = `
        <section class="card tool tuner">
          <div class="tuner__note"><strong data-tuner-note>—</strong><span data-tuner-freq>對準麥克風，拉一個長音</span></div>
          <div class="tuner__meter">
            <div class="tuner__scale"><span>-50</span><span>-25</span><span>0</span><span>+25</span><span>+50</span></div>
            <div class="tuner__track"><i class="tuner__center"></i><i class="tuner__needle" data-tuner-needle></i></div>
            <div class="tuner__cents" data-tuner-cents>—</div>
          </div>
          <div class="row row--center" style="margin-top:14px">
            <button class="btn btn--big btn--primary" data-tuner-toggle>${tuner?.running ? '■ 停止' : '🎤 開始調音'}</button>
          </div>
          <div class="row row--wrap row--center" style="margin-top:14px">
            ${OPEN_STRINGS.map((s) => `<button class="chip" data-pluck="${s.midi}">${s.name} ${midiToFreq(s.midi, audio.a4).toFixed(1)}Hz</button>`).join('')}
          </div>
          <label class="field" style="margin-top:14px"><span class="field__label">基準音 A4（${audio.a4} Hz）</span>
            <input class="slider" type="range" min="432" max="446" value="${audio.a4}" data-a4>
          </label>
          <p class="muted small">綠燈 = ±5 分以內。弦樂器請以空弦與泛音校正，不要只信數字。</p>
        </section>`;

      const noteEl = $('[data-tuner-note]', root);
      const freqEl = $('[data-tuner-freq]', root);
      const centsEl = $('[data-tuner-cents]', root);
      const needle = $('[data-tuner-needle]', root);
      const toggle = $('[data-tuner-toggle]', root);

      const onReading = (reading) => {
        if (!reading) {
          noteEl.textContent = '—';
          noteEl.className = '';
          freqEl.textContent = '拉一個長音…';
          centsEl.textContent = '—';
          needle.style.transform = 'translateX(-50%)';
          return;
        }
        const { name, octave, cents, freq } = reading;
        noteEl.textContent = `${name}${octave}`;
        noteEl.className = Math.abs(cents) <= 5 ? 'is-intune' : (Math.abs(cents) <= 15 ? 'is-close' : '');
        freqEl.textContent = `${freq.toFixed(1)} Hz`;
        centsEl.textContent = `${cents > 0 ? '+' : ''}${cents} 分`;
        needle.style.transform = `translateX(calc(-50% + ${clamp(cents, -50, 50) * 1.9}px))`;
      };

      toggle.addEventListener('click', async () => {
        if (tuner?.running) {
          tuner.stop();
          tuner = null;
          toggle.textContent = '🎤 開始調音';
          onReading(null);
          return;
        }
        try {
          tuner = new Tuner();
          await tuner.start(onReading, audio.a4);
          toggle.textContent = '■ 停止';
        } catch (err) {
          tuner = null;
          toast(err.message || '無法取得麥克風權限', 'bad');
        }
      });

      $$('[data-pluck]', root).forEach((b) => b.addEventListener('click', () => audio.pluck(Number(b.dataset.pluck))));
      $('[data-a4]', root).addEventListener('change', (e) => {
        audio.a4 = Number(e.target.value);
        setSetting('a4', audio.a4);
        renderTuner();
      });
    }

    /* ---------------------------------------------------------- timer */

    function renderTimer() {
      pane().innerHTML = `
        <section class="card tool">
          <div class="timer__display" data-timer-display>${formatClock(session.elapsed())}</div>
          <p class="muted" style="text-align:center">${esc(session.active?.title || '自由練習')}</p>
          <div class="row row--center" style="margin:14px 0">
            <button class="btn btn--big ${session.running ? 'btn--danger' : 'btn--primary'}" data-timer-toggle>${session.running ? '⏸ 暫停' : '▶︎ 開始'}</button>
            <button class="btn btn--ghost btn--big" data-timer-stop>■ 結束並記錄</button>
          </div>
          <p class="muted small" style="text-align:center">計時會累加到今天的練習時數；沒有綁定任務時記為自由練習。</p>
        </section>

        ${sectionTitle('倒數計時')}
        <section class="card tool">
          <div class="row row--wrap row--center">
            ${[5, 10, 15, 20, 25, 45].map((m) => `<button class="chip chip--lg" data-count="${m}">${m} 分</button>`).join('')}
          </div>
          <div class="timer__display timer__display--sm" data-countdown>—</div>
          <div class="row row--center"><button class="btn btn--ghost" data-count-stop>取消倒數</button></div>
          <p class="muted small" style="text-align:center">時間到會響三聲，適合分段練習與休息控制。</p>
        </section>`;

      $('[data-timer-toggle]', root).addEventListener('click', () => {
        session.toggle({ freeform: true, title: session.active?.title || '自由練習' });
        renderTimer();
      });
      $('[data-timer-stop]', root).addEventListener('click', () => {
        const total = session.stop();
        if (total > 30) toast(`已記錄 ${Math.round(total / 60)} 分鐘練習`, 'good');
        renderTimer();
      });
      $$('[data-count]', root).forEach((b) => b.addEventListener('click', () => {
        const mins = Number(b.dataset.count);
        countdown = { endsAt: Date.now() + mins * 60000, total: mins * 60 };
        audio.ensure();
        toast(`開始 ${mins} 分鐘倒數`);
      }));
      $('[data-count-stop]', root).addEventListener('click', () => { countdown = null; $('[data-countdown]', root).textContent = '—'; });
    }

    /* ------------------------------------------------------ lifecycle */

    shell();

    timerInterval = setInterval(() => {
      const display = $('[data-timer-display]', root);
      if (display) display.textContent = formatClock(session.elapsed());
      const cd = $('[data-countdown]', root);
      if (cd && countdown) {
        const left = (countdown.endsAt - Date.now()) / 1000;
        if (left <= 0) {
          cd.textContent = '時間到';
          [0, 0.3, 0.6].forEach((d) => setTimeout(() => audio.pluck(88, 0.4), d * 1000));
          countdown = null;
          toast('倒數結束', 'good');
        } else {
          cd.textContent = formatClock(left);
        }
      }
    }, 500);

    return () => {
      clearInterval(timerInterval);
      if (offBeat) offBeat();
      if (tuner) { tuner.stop(); tuner = null; }
    };
  },
};
