// Today: adaptive quests, live practice timers, the daily boss, and momentum.

import {
  state, stats, ensureToday, todayKey, toggleTask, rerollToday, setBoss,
  setDayField, weakSkills, minutesSeries, dayMinutes, isDayComplete, DAY_COMPLETE_RATIO,
} from '../state.js';
import { skillLabel, TOOL_LABELS, PHASES, currentPhaseIndex } from '../content.js';
import { session } from '../session.js';
import { navigate } from '../router.js';
import {
  pageHead, statPills, ring, statTile, sectionTitle, minutesChart, progressBar, emptyState,
} from '../components.js';
import { icon } from '../icons.js';
import { $, $$, esc, pct, formatClock, formatDate, addDays, weekStart, toast, formatMinutes } from '../util.js';

function greeting() {
  const h = new Date().getHours();
  if (h < 5) return '深夜練琴';
  if (h < 11) return '早安';
  if (h < 14) return '午安';
  if (h < 18) return '下午好';
  return '晚安';
}

const TOOL_ICONS = { metronome: 'metronome', drone: 'tone', tuner: 'gauge', record: 'mic' };

function taskCard(task, index, activeIndex) {
  const spent = task.spent || 0;
  const isActive = activeIndex === index;
  const ratio = task.mins ? Math.min(100, (spent / 60 / task.mins) * 100) : 0;
  const tools = (task.tools || []).map((t) => `<button class="chip" data-tool="${esc(t)}" data-task="${index}">${icon(TOOL_ICONS[t] || 'sparkle')}${esc(TOOL_LABELS[t] || t)}</button>`).join('');
  return `<article class="quest ${task.done ? 'is-done' : ''} ${isActive ? 'is-active' : ''}" data-index="${index}">
    <button class="quest__check" data-toggle="${index}" aria-label="${task.done ? '取消完成' : '標記完成'}">${icon('check')}</button>
    <div class="quest__body">
      <div class="quest__top">
        <h3>${esc(task.title)}</h3>
        <span class="quest__cat">${esc(skillLabel(task.cat))}</span>
      </div>
      <p>${esc(task.desc)}</p>
      <div class="quest__meta">
        <span>${task.mins} 分鐘</span><span>·</span><span>${task.xp} XP</span>
        <span>·</span><span class="quest__spent" data-elapsed="${index}">${formatClock(spent)}</span>
      </div>
      ${progressBar(ratio)}
      <div class="quest__tools">
        <button class="chip chip--primary" data-timer="${index}">${isActive && session.running ? `${icon('pause')}暫停` : `${icon('play')}開始計時`}</button>
        ${tools}
      </div>
    </div>
  </article>`;
}

export const dashboardView = {
  id: 'dashboard',
  label: '今日',
  title: '今日訓練',
  icon: 'target',
  primary: true,

  mount(root) {
    let unsubscribeSession = null;
    let uiTimer = null;

    const render = () => {
      const day = ensureToday();
      const s = stats();
      const key = todayKey();
      const doneCount = day.tasks.filter((t) => t.done).length;
      const completion = day.tasks.length ? (doneCount / day.tasks.length) * 100 : 0;
      const minutes = dayMinutes(day);
      const goal = state.profile.dailyMinutes || 180;
      const planned = day.tasks.reduce((a, t) => a + t.mins, 0);
      const todayXp = day.tasks.filter((t) => t.done).reduce((a, t) => a + t.xp, 0) + (day.boss?.done ? 60 : 0);
      const weak = weakSkills().map(skillLabel).join('、');
      const phase = PHASES[currentPhaseIndex(s)];
      const yesterdayFocus = state.days[addDays(key, -1)]?.nextFocus;
      const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart(key), i))
        .filter((k) => dayMinutes(state.days[k]) > 0).length;
      const active = session.active && session.active.dayKey === key ? session.active.taskIndex : -1;

      root.innerHTML = `
        ${pageHead(`${greeting()}${state.profile.name ? `，${state.profile.name}` : ''}`, `${formatDate(key)}｜最弱能力：${weak}`, statPills(s))}

        ${yesterdayFocus ? `<div class="callout"><span class="callout__icon">${icon('pin')}</span><div><strong>昨天寫下的第一優先</strong><p>${esc(yesterdayFocus)}</p></div></div>` : ''}

        <section class="card hero">
          <div class="hero__info">
            <span class="badge">${esc(phase.lv)} ${esc(phase.name)}</span>
            <h2>${esc(state.profile.mainWork || '尚未設定主曲目')}</h2>
            <p class="muted">今日任務會優先補強能力面板最低分項目，以及最近沒完成的項目。</p>
            <div class="hero__xp">
              <div class="row row--between"><span class="muted">LV.${s.level} → LV.${s.level + 1}</span><span class="muted">${s.into} / ${s.span} XP</span></div>
              ${progressBar(s.ratio * 100, 'gold')}
            </div>
          </div>
          <div class="hero__ring">${ring(completion, `${pct(completion)}%`, `${doneCount}/${day.tasks.length} 任務`)}</div>
        </section>

        <div class="tiles">
          ${statTile('今日已練', formatMinutes(minutes), `目標 ${goal} 分`, minutes >= goal ? 'good' : '')}
          ${statTile('任務時數', `${planned} 分`, '今日派發總量')}
          ${statTile('今日 XP', todayXp, '完成任務所得')}
          ${statTile('連勝', `${s.streak} 天`, `最佳 ${s.bestStreak} 天`, s.streak > 0 ? 'flame' : '')}
        </div>

        ${sectionTitle('今日主線', `<button class="btn btn--ghost btn--sm" data-action="reroll">重新派發</button>`)}
        <div class="quests">
          ${day.tasks.length
            ? day.tasks.map((t, i) => taskCard(t, i, active)).join('')
            : emptyState('scroll', '今天還沒有任務', '按「重新派發」產生今日訓練菜單。')}
        </div>

        ${sectionTitle('今日 Boss')}
        <section class="card boss ${day.boss?.done ? 'is-done' : ''}">
          <div class="boss__head">
            <span class="badge badge--dark">TODAY BOSS</span>
            ${day.boss?.done ? '<span class="badge badge--gold">已通過</span>' : ''}
          </div>
          <h2>${esc(state.profile.mainWork || '主曲目')}：不重來驗收</h2>
          <p>連續 8–12 分鐘不中斷。驗收標準：節拍不崩、重大音準事故 ≤ 3 處、失誤後仍能繼續、結束後可列出 3 個明確修正點。</p>
          <label class="boss__score">
            <span>自評分數 <b data-boss-score>${day.boss?.score || 0}</b></span>
            <input type="range" min="0" max="100" value="${day.boss?.score || 0}" data-boss-range>
          </label>
          <textarea class="input" rows="2" placeholder="錄完後立刻寫下 3 個問題…" data-boss-notes>${esc(day.boss?.notes || '')}</textarea>
          <div class="row row--wrap" style="margin-top:12px">
            <button class="btn ${day.boss?.done ? 'btn--ghost-light' : 'btn--gold'}" data-action="boss">${day.boss?.done ? '取消完成' : '完成 Boss'}</button>
            <button class="btn btn--ghost-light" data-action="record">${icon('mic')}直接錄音</button>
          </div>
        </section>

        ${sectionTitle('最近 14 天')}
        <section class="card">
          ${minutesChart(minutesSeries(14), goal)}
          <div class="row row--between" style="margin-top:10px">
            <span class="muted small">本週已練 ${weekDays} / ${state.profile.weeklyDays} 天</span>
            <span class="muted small">${isDayComplete(day) ? '今天已達標 ✅' : `完成 ${Math.round(DAY_COMPLETE_RATIO * 100)}% 任務即計入連勝`}</span>
          </div>
        </section>

        <section class="card">
          <h3>明日第一優先</h3>
          <textarea class="input" rows="2" placeholder="結束前寫下明天最先要修的一件事…" data-next-focus>${esc(day.nextFocus || '')}</textarea>
          <div class="row row--end" style="margin-top:10px"><button class="btn btn--sm" data-action="saveFocus">儲存</button></div>
        </section>`;

      bind();
    };

    const bind = () => {
      root.querySelectorAll('[data-toggle]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const i = Number(btn.dataset.toggle);
          const wasDone = ensureToday().tasks[i].done;
          if (!wasDone && session.active?.taskIndex === i) session.pause();
          toggleTask(i);
          if (!wasDone) toast(`完成：${ensureToday().tasks[i].title}`, 'good');
          render();
        });
      });

      root.querySelectorAll('[data-timer]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const i = Number(btn.dataset.timer);
          const task = ensureToday().tasks[i];
          if (session.active?.taskIndex === i && session.running) session.pause();
          else session.start({ taskIndex: i, title: task.title });
          render();
        });
      });

      root.querySelectorAll('[data-tool]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const tool = btn.dataset.tool;
          const i = Number(btn.dataset.task);
          const task = ensureToday().tasks[i];
          if (!session.active) session.start({ taskIndex: i, title: task.title });
          if (tool === 'record') navigate('recordings', ['new']);
          else navigate('practice', [tool]);
        });
      });

      const rangeEl = $('[data-boss-range]', root);
      if (rangeEl) {
        rangeEl.addEventListener('input', () => { $('[data-boss-score]', root).textContent = rangeEl.value; });
        rangeEl.addEventListener('change', () => setBoss({ score: Number(rangeEl.value) }));
      }
      const notesEl = $('[data-boss-notes]', root);
      if (notesEl) notesEl.addEventListener('change', () => setBoss({ notes: notesEl.value }));

      $$('[data-action]', root).forEach((btn) => {
        btn.addEventListener('click', () => {
          const action = btn.dataset.action;
          if (action === 'reroll') { rerollToday(); toast('已重新派發今日任務'); render(); }
          if (action === 'boss') {
            const day = ensureToday();
            const next = !day.boss?.done;
            setBoss({ done: next, score: next ? Number($('[data-boss-range]', root)?.value || 0) : day.boss.score });
            if (next) toast('Boss 通過，+60 XP', 'good');
            render();
          }
          if (action === 'record') navigate('recordings', ['new']);
          if (action === 'saveFocus') {
            setDayField('nextFocus', $('[data-next-focus]', root).value.trim());
            toast('已儲存明日第一優先', 'good');
          }
        });
      });
    };

    render();

    // Live-update the elapsed label of the running quest without re-rendering.
    uiTimer = setInterval(() => {
      const active = session.active;
      if (!active || !session.running) return;
      const label = root.querySelector(`[data-elapsed="${active.taskIndex}"]`);
      if (label) label.textContent = formatClock(session.elapsed());
    }, 1000);

    unsubscribeSession = session.subscribe(() => {
      const btns = root.querySelectorAll('[data-timer]');
      btns.forEach((btn) => {
        const i = Number(btn.dataset.timer);
        const isActive = session.active?.taskIndex === i && session.running;
        btn.innerHTML = isActive ? `${icon('pause')}暫停` : `${icon('play')}開始計時`;
        btn.closest('.quest')?.classList.toggle('is-active', isActive);
      });
    });

    return () => {
      clearInterval(uiTimer);
      if (unsubscribeSession) unsubscribeSession();
    };
  },
};
