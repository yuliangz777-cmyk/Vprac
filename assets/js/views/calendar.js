// Training calendar: a month at a glance, with per-day detail.

import { state, dayMinutes, isDayComplete, todayKey } from '../state.js';
import { skillLabel } from '../content.js';
import { pageHead, statTile, emptyState } from '../components.js';
import { $$, esc, openModal, dateKey, formatDate, formatMinutes } from '../util.js';

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

export const calendarView = {
  id: 'calendar',
  label: '日曆',
  title: '訓練日曆',
  icon: '📅',

  mount(root) {
    const now = new Date();
    let year = now.getFullYear();
    let month = now.getMonth();

    const render = () => {
      const first = new Date(year, month, 1);
      const last = new Date(year, month + 1, 0);
      const offset = (first.getDay() + 6) % 7; // Monday-first grid
      const goal = state.profile.dailyMinutes || 180;

      let cells = '';
      for (let i = 0; i < offset; i += 1) cells += '<div class="cal__cell cal__cell--pad"></div>';
      let monthMinutes = 0;
      let activeDays = 0;
      for (let d = 1; d <= last.getDate(); d += 1) {
        const key = dateKey(new Date(year, month, d));
        const day = state.days[key];
        const minutes = dayMinutes(day);
        monthMinutes += minutes;
        if (minutes > 0) activeDays += 1;
        const level = minutes === 0 ? 0 : Math.min(4, Math.ceil((minutes / goal) * 4));
        const classes = [
          'cal__cell',
          level ? `is-l${level}` : '',
          key === todayKey() ? 'is-today' : '',
          isDayComplete(day) ? 'is-complete' : '',
        ].filter(Boolean).join(' ');
        cells += `<button class="${classes}" data-day="${key}">
          <span class="cal__num">${d}</span>
          ${minutes ? `<span class="cal__min">${minutes}</span>` : ''}
          ${day?.boss?.done ? '<i class="cal__boss">👑</i>' : ''}
        </button>`;
      }

      root.innerHTML = `
        ${pageHead('訓練日曆', '顏色越深代表當天練得越多；皇冠代表當天通過 Boss。')}
        <div class="tiles">
          ${statTile('本月練習', formatMinutes(monthMinutes), `${activeDays} 天有練`)}
          ${statTile('月均', activeDays ? formatMinutes(monthMinutes / activeDays) : '—', '有練的日子')}
          ${statTile('達標日', String(Object.keys(state.days).filter((k) => k.startsWith(`${year}-${String(month + 1).padStart(2, '0')}`) && isDayComplete(state.days[k])).length), '計入連勝')}
        </div>
        <section class="card">
          <div class="row row--between cal__head">
            <button class="icon-btn" data-move="-1" aria-label="上個月">‹</button>
            <strong>${year} 年 ${month + 1} 月</strong>
            <button class="icon-btn" data-move="1" aria-label="下個月">›</button>
          </div>
          <div class="cal">
            ${WEEKDAYS.map((w) => `<div class="cal__dow">${w}</div>`).join('')}
            ${cells}
          </div>
          <div class="cal__legend">
            <span class="muted small">少</span>
            ${[1, 2, 3, 4].map((l) => `<i class="cal__swatch is-l${l}"></i>`).join('')}
            <span class="muted small">多</span>
          </div>
        </section>`;

      $$('[data-move]', root).forEach((btn) => btn.addEventListener('click', () => {
        month += Number(btn.dataset.move);
        if (month < 0) { month = 11; year -= 1; }
        if (month > 11) { month = 0; year += 1; }
        render();
      }));

      $$('[data-day]', root).forEach((btn) => btn.addEventListener('click', () => showDay(btn.dataset.day)));
    };

    const showDay = (key) => {
      const day = state.days[key];
      const minutes = dayMinutes(day);
      const body = !day || (!day.tasks.length && !minutes)
        ? emptyState('🌙', '這天沒有紀錄', '休息也是訓練的一部分。')
        : `
          <div class="tiles tiles--sm">
            ${statTile('練習時間', formatMinutes(minutes))}
            ${statTile('完成任務', `${day.tasks.filter((t) => t.done).length}/${day.tasks.length}`)}
            ${statTile('Boss', day.boss?.done ? `通過 ${day.boss.score || 0}` : '未完成')}
          </div>
          <ul class="checklist" style="margin-top:12px">
            ${day.tasks.map((t) => `<li class="${t.done ? 'is-ok' : ''}"><span>${t.done ? '✓' : '○'}</span>${esc(t.title)} <i class="muted">· ${esc(skillLabel(t.cat))}</i></li>`).join('')}
          </ul>
          ${day.notes ? `<div class="note-block"><b>筆記</b><p>${esc(day.notes)}</p></div>` : ''}
          ${day.nextFocus ? `<div class="note-block"><b>隔日第一優先</b><p>${esc(day.nextFocus)}</p></div>` : ''}
          ${day.boss?.notes ? `<div class="note-block"><b>Boss 檢討</b><p>${esc(day.boss.notes)}</p></div>` : ''}`;
      openModal(formatDate(key), body);
    };

    render();
  },
};
