// Competition centre: countdown, readiness gap, and a record of every entry.

import { state, stats, addCompetition, updateCompetition, removeCompetition, setProfile } from '../state.js';
import { pageHead, sectionTitle, statTile, emptyState, progressBar } from '../components.js';
import { $, $$, esc, openModal, confirmDialog, toast, dateKey, daysBetween, formatDate } from '../util.js';

function compForm(entry = {}) {
  return `
    <label class="field"><span class="field__label">賽事名稱</span><input class="input" data-f="name" value="${esc(entry.name || '')}" placeholder="例：Menuhin Competition"></label>
    <label class="field"><span class="field__label">日期</span><input class="input" type="date" data-f="date" value="${esc(entry.date || '')}"></label>
    <label class="field"><span class="field__label">結果</span><input class="input" data-f="result" value="${esc(entry.result || '')}" placeholder="待賽 / 入圍 / Semifinal / 3rd Prize"></label>
    <label class="field"><span class="field__label">備註</span><textarea class="input" rows="3" data-f="notes" placeholder="規章曲目、報名截止、評審回饋…">${esc(entry.notes || '')}</textarea></label>
    <div class="row row--end" style="margin-top:14px">
      ${entry.id ? '<button class="btn btn--ghost btn--danger" data-delete>刪除</button>' : ''}
      <button class="btn btn--primary" data-save>儲存</button>
    </div>`;
}

const readValues = (modal) => {
  const out = {};
  $$('[data-f]', modal).forEach((el) => { out[el.dataset.f] = el.value.trim(); });
  return out;
};

/** Weeks left vs. how ready the main piece is: the number that matters. */
function readinessAdvice(daysLeft, readiness) {
  if (daysLeft === null) return '設定目標比賽日期後，這裡會反推每週該達到的成熟度。';
  if (daysLeft < 0) return '比賽日期已過，記得把結果登錄到比賽紀錄。';
  const weeks = Math.max(1, Math.ceil(daysLeft / 7));
  const need = Math.max(0, 95 - readiness);
  const perWeek = (need / weeks).toFixed(1);
  if (need === 0) return '主曲目已達 95%，接下來重點是模擬演出與穩定度，不是再多練音符。';
  return `還有 ${weeks} 週。主曲目要從 ${readiness}% 推到 95%，平均每週需要 +${perWeek}%。做不到就該減少曲目數量，而不是壓縮驗收標準。`;
}

export const competitionView = {
  id: 'competition',
  label: '比賽',
  title: '比賽中心',
  icon: '🏆',

  mount(root) {
    const render = () => {
      const s = stats();
      const p = state.profile;
      const today = dateKey();
      const daysLeft = p.competitionDate ? daysBetween(today, p.competitionDate) : null;
      const perfLeft = p.performanceDate ? daysBetween(today, p.performanceDate) : null;
      const main = state.repertoire.slice().sort((a, b) => b.readiness - a.readiness)[0];

      root.innerHTML = `
        ${pageHead('比賽中心', '用倒數天數反推曲目成熟度與模擬頻率。')}

        <div class="tiles">
          ${statTile('距離目標比賽', daysLeft === null ? '—' : `${daysLeft} 天`, p.competitionName || p.competitionDate || '尚未設定', daysLeft !== null && daysLeft < 30 ? 'flame' : '')}
          ${statTile('距離下次演出', perfLeft === null ? '—' : `${perfLeft} 天`, p.performanceDate || '尚未設定')}
          ${statTile('主曲目成熟度', `${s.maxReadiness}%`, main ? main.work : '—', s.maxReadiness >= 80 ? 'good' : '')}
        </div>

        <section class="card">
          <h3>目標</h3>
          <p>${esc(p.target || '尚未設定目標')}</p>
          ${progressBar(s.maxReadiness, s.maxReadiness >= 80 ? 'good' : 'gold')}
          <p class="muted small" style="margin-top:10px">${esc(readinessAdvice(daysLeft, s.maxReadiness))}</p>
          <div class="grid-2" style="margin-top:12px">
            <label class="field"><span class="field__label">目標賽事名稱</span><input class="input" data-p="competitionName" value="${esc(p.competitionName || '')}" placeholder="例：Sibelius Competition"></label>
            <label class="field"><span class="field__label">比賽日期</span><input class="input" type="date" data-p="competitionDate" value="${esc(p.competitionDate || '')}"></label>
            <label class="field"><span class="field__label">下次演出日期</span><input class="input" type="date" data-p="performanceDate" value="${esc(p.performanceDate || '')}"></label>
            <label class="field"><span class="field__label">長期目標</span><input class="input" data-p="target" value="${esc(p.target || '')}"></label>
          </div>
        </section>

        ${sectionTitle('比賽紀錄', '<button class="btn btn--sm btn--primary" data-add>＋ 新增紀錄</button>')}
        <div class="stack">
          ${state.competitions.length ? state.competitions.map((c) => `
            <article class="card event">
              <div class="event__date">${esc(c.date ? formatDate(c.date) : '未定')}</div>
              <div class="event__body">
                <div class="row row--between"><strong>${esc(c.name)}</strong><button class="btn btn--ghost btn--sm" data-edit="${esc(c.id)}">編輯</button></div>
                <p class="muted">${esc(c.result || '待賽')}${c.notes ? ` · ${esc(c.notes)}` : ''}</p>
              </div>
            </article>`).join('')
            : emptyState('🏅', '還沒有比賽紀錄', '把報名中、準備中、已完成的賽事都記下來，包含評審回饋。')}
        </div>`;

      $$('[data-p]', root).forEach((input) => input.addEventListener('change', () => {
        setProfile({ [input.dataset.p]: input.value });
        toast('已更新', 'good');
        render();
      }));

      $('[data-add]', root).addEventListener('click', () => {
        openModal('新增比賽紀錄', compForm(), (modal, close) => {
          $('[data-save]', modal).addEventListener('click', () => {
            const values = readValues(modal);
            if (!values.name) { toast('請輸入賽事名稱', 'bad'); return; }
            addCompetition(values);
            close();
            render();
          });
        });
      });

      $$('[data-edit]', root).forEach((btn) => btn.addEventListener('click', () => {
        const item = state.competitions.find((c) => c.id === btn.dataset.edit);
        if (!item) return;
        openModal('編輯比賽紀錄', compForm(item), (modal, close) => {
          $('[data-save]', modal).addEventListener('click', () => {
            updateCompetition(item.id, readValues(modal));
            close();
            render();
          });
          $('[data-delete]', modal).addEventListener('click', async () => {
            close();
            if (await confirmDialog('刪除紀錄', `確定刪除「${item.name}」？`, '刪除')) {
              removeCompetition(item.id);
              render();
            }
          });
        });
      }));
    };

    render();
  },
};
