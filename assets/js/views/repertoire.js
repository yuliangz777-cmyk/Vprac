// Repertoire library: what you are learning, how ready each piece is.

import { state, addRepertoire, updateRepertoire, removeRepertoire } from '../state.js';
import { STATUS_LABELS } from '../content.js';
import { pageHead, sectionTitle, progressBar, emptyState, statTile } from '../components.js';
import { icon } from '../icons.js';
import { $, $$, esc, openModal, confirmDialog, toast } from '../util.js';

function form(entry = {}) {
  return `
    <label class="field"><span class="field__label">作品</span><input class="input" data-f="work" value="${esc(entry.work || '')}" placeholder="例：Sibelius Violin Concerto"></label>
    <label class="field"><span class="field__label">範圍 / 樂章</span><input class="input" data-f="part" value="${esc(entry.part || '')}" placeholder="例：第一樂章＋Cadenza"></label>
    <label class="field"><span class="field__label">狀態</span>
      <select class="input" data-f="status">
        ${Object.entries(STATUS_LABELS).map(([k, v]) => `<option value="${k}" ${entry.status === k ? 'selected' : ''}>${v}</option>`).join('')}
      </select>
    </label>
    <label class="field"><span class="field__label">成熟度 <b data-readiness-out>${entry.readiness ?? 0}</b>%</span>
      <input class="slider" type="range" min="0" max="100" value="${entry.readiness ?? 0}" data-f="readiness">
    </label>
    <label class="field"><span class="field__label">備註</span><textarea class="input" rows="3" data-f="notes" placeholder="老師交代、比賽規章要求、待解決段落…">${esc(entry.notes || '')}</textarea></label>
    <div class="row row--end" style="margin-top:14px">
      ${entry.id ? '<button class="btn btn--danger btn--ghost" data-delete>刪除</button>' : ''}
      <button class="btn btn--primary" data-save>儲存</button>
    </div>`;
}

function readValues(root) {
  const out = {};
  $$('[data-f]', root).forEach((el) => { out[el.dataset.f] = el.type === 'range' ? Number(el.value) : el.value.trim(); });
  return out;
}

export const repertoireView = {
  id: 'repertoire',
  label: '曲目',
  title: '曲目庫',
  icon: 'book',
  primary: true,

  mount(root) {
    const render = () => {
      const list = state.repertoire;
      const ready = list.filter((r) => r.readiness >= 80).length;
      const avg = list.length ? Math.round(list.reduce((a, r) => a + r.readiness, 0) / list.length) : 0;

      root.innerHTML = `
        ${pageHead('曲目庫', '追蹤每首作品從 Learning 到 Competition-ready 的成熟度。')}
        <div class="tiles">
          ${statTile('曲目總數', list.length, '含計畫中')}
          ${statTile('可上場', ready, '成熟度 ≥ 80%', ready ? 'good' : '')}
          ${statTile('平均成熟度', `${avg}%`, '全部曲目')}
        </div>
        ${sectionTitle('清單', `<button class="btn btn--sm btn--primary" data-add>${icon('plus')}新增曲目</button>`)}
        <div class="rep-list">
          ${list.length ? list.map((r) => `
            <article class="card rep" data-id="${esc(r.id)}">
              <div class="rep__head">
                <div>
                  <h3>${esc(r.work)}</h3>
                  <p class="muted small">${esc(r.part || '—')}</p>
                </div>
                <span class="status status--${esc(r.status)}">${esc(STATUS_LABELS[r.status] || r.status)}</span>
              </div>
              ${progressBar(r.readiness, r.readiness >= 80 ? 'good' : '')}
              <div class="rep__foot">
                <input class="slider" type="range" min="0" max="100" value="${r.readiness}" data-ready="${esc(r.id)}">
                <output data-ready-out="${esc(r.id)}">${r.readiness}%</output>
                <button class="btn btn--ghost btn--sm" data-edit="${esc(r.id)}">編輯</button>
              </div>
              ${r.notes ? `<p class="rep__notes">${esc(r.notes)}</p>` : ''}
            </article>`).join('')
            : emptyState('note', '曲目庫是空的', '把老師給的曲目、比賽規章要求的曲目都放進來。')}
        </div>`;

      $('[data-add]', root).addEventListener('click', () => {
        openModal('新增曲目', form({ status: 'planned', readiness: 0 }), (modal, close) => {
          const range = $('[data-f="readiness"]', modal);
          range.addEventListener('input', () => { $('[data-readiness-out]', modal).textContent = range.value; });
          $('[data-save]', modal).addEventListener('click', () => {
            const values = readValues(modal);
            if (!values.work) { toast('請輸入作品名稱', 'bad'); return; }
            addRepertoire(values);
            close();
            toast('已新增曲目', 'good');
            render();
          });
        });
      });

      $$('[data-edit]', root).forEach((btn) => btn.addEventListener('click', () => {
        const item = state.repertoire.find((r) => r.id === btn.dataset.edit);
        if (!item) return;
        openModal('編輯曲目', form(item), (modal, close) => {
          const range = $('[data-f="readiness"]', modal);
          range.addEventListener('input', () => { $('[data-readiness-out]', modal).textContent = range.value; });
          $('[data-save]', modal).addEventListener('click', () => {
            updateRepertoire(item.id, readValues(modal));
            close();
            toast('已更新', 'good');
            render();
          });
          $('[data-delete]', modal).addEventListener('click', async () => {
            close();
            if (await confirmDialog('刪除曲目', `確定要刪除「${item.work}」？此動作無法復原。`, '刪除')) {
              removeRepertoire(item.id);
              toast('已刪除');
              render();
            }
          });
        });
      }));

      $$('[data-ready]', root).forEach((input) => {
        const out = root.querySelector(`[data-ready-out="${input.dataset.ready}"]`);
        input.addEventListener('input', () => { out.textContent = `${input.value}%`; });
        input.addEventListener('change', () => { updateRepertoire(input.dataset.ready, { readiness: Number(input.value) }); render(); });
      });
    };

    render();
  },
};
