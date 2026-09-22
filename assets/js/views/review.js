// Acceptance: turn "I practised" into "I passed a repeatable standard".

import {
  state, ensureToday, todayKey, setCheck, setDayField, addWeeklyReview, removeWeeklyReview,
} from '../state.js';
import { pageHead, sectionTitle, progressBar, emptyState, card } from '../components.js';
import { icon } from '../icons.js';
import { $, $$, esc, toast, formatDate, weekLabel, confirmDialog } from '../util.js';

export const reviewView = {
  id: 'review',
  label: '驗收',
  title: '驗收與回顧',
  icon: 'checkCircle',
  primary: true,

  mount(root) {
    const render = () => {
      const day = ensureToday();
      const daily = state.acceptance.daily;
      const weekly = state.acceptance.weekly;
      const dailyDone = daily.filter((_, i) => day.checks[i]).length;
      const weeklyDone = weekly.filter((_, i) => day.weekChecks[i]).length;

      root.innerHTML = `
        ${pageHead('驗收與回顧', '把「有練」改成「通過可重複驗收的標準」。')}

        <div class="split">
          ${card(`
            <div class="row row--between"><h3>每日驗收</h3><span class="muted small">${dailyDone}/${daily.length}</span></div>
            ${progressBar((dailyDone / daily.length) * 100, dailyDone === daily.length ? 'good' : '')}
            <ul class="checklist checklist--interactive">
              ${daily.map((text, i) => `<li>
                <label><input type="checkbox" data-check="daily:${i}" ${day.checks[i] ? 'checked' : ''}><span>${esc(text)}</span></label>
              </li>`).join('')}
            </ul>
            ${dailyDone === daily.length ? '<p class="muted small">五項全過，今天 +30 XP。</p>' : ''}`)}

          ${card(`
            <div class="row row--between"><h3>本週驗收</h3><span class="muted small">${weeklyDone}/${weekly.length}</span></div>
            ${progressBar((weeklyDone / weekly.length) * 100, weeklyDone === weekly.length ? 'good' : '')}
            <ul class="checklist checklist--interactive">
              ${weekly.map((text, i) => `<li>
                <label><input type="checkbox" data-check="weekly:${i}" ${day.weekChecks[i] ? 'checked' : ''}><span>${esc(text)}</span></label>
              </li>`).join('')}
            </ul>`)}
        </div>

        ${sectionTitle('今日訓練筆記')}
        <section class="card">
          <textarea class="input" rows="5" data-notes placeholder="今天最嚴重的三個問題（寫小節號）、什麼練法有效、老師講了什麼…">${esc(day.notes || '')}</textarea>
          <div class="row row--end" style="margin-top:10px"><button class="btn btn--primary btn--sm" data-save-notes>儲存筆記</button></div>
        </section>

        ${sectionTitle('週回顧')}
        <section class="card">
          <p class="muted small">${esc(weekLabel(todayKey()))}</p>
          <div class="grid-2">
            <label class="field"><span class="field__label">本週 3 項進步</span><textarea class="input" rows="4" data-wins placeholder="1.&#10;2.&#10;3."></textarea></label>
            <label class="field"><span class="field__label">下週 3 項修正</span><textarea class="input" rows="4" data-fixes placeholder="1.&#10;2.&#10;3."></textarea></label>
          </div>
          <div class="row row--end" style="margin-top:10px"><button class="btn btn--primary btn--sm" data-save-weekly>存入週回顧（+40 XP）</button></div>
        </section>

        ${sectionTitle('回顧紀錄')}
        <div class="stack">
          ${state.weeklyReviews.length ? state.weeklyReviews.map((w) => `
            <article class="card review-entry">
              <div class="row row--between">
                <strong>${esc(formatDate(w.date))}</strong>
                <button class="icon-btn" data-del-review="${esc(w.id)}" aria-label="刪除">${icon('trash')}</button>
              </div>
              ${w.wins ? `<p><b>進步：</b>${esc(w.wins)}</p>` : ''}
              ${w.fixes ? `<p><b>修正：</b>${esc(w.fixes)}</p>` : ''}
            </article>`).join('')
            : emptyState('book', '還沒有週回顧', '每週一次，寫 3 項進步與 3 項修正就好。')}
        </div>`;

      $$('[data-check]', root).forEach((box) => box.addEventListener('change', () => {
        const [kind, index] = box.dataset.check.split(':');
        setCheck(kind, index, box.checked);
        render();
      }));

      $('[data-save-notes]', root).addEventListener('click', () => {
        setDayField('notes', $('[data-notes]', root).value);
        toast('今日筆記已儲存', 'good');
      });

      $('[data-save-weekly]', root).addEventListener('click', () => {
        const wins = $('[data-wins]', root).value.trim();
        const fixes = $('[data-fixes]', root).value.trim();
        if (!wins && !fixes) { toast('至少填一欄再儲存', 'bad'); return; }
        addWeeklyReview({ wins, fixes });
        toast('週回顧已儲存，+40 XP', 'good');
        render();
      });

      $$('[data-del-review]', root).forEach((btn) => btn.addEventListener('click', async () => {
        if (await confirmDialog('刪除回顧', '確定刪除這筆週回顧？', '刪除')) {
          removeWeeklyReview(btn.dataset.delReview);
          render();
        }
      }));
    };

    render();
  },
};
