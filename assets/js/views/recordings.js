// Recording library: capture takes, play them back, keep the honest ones.

import { recordingsDB } from '../db.js';
import { TakeRecorder, saveTake, recorderSupported } from '../recorder.js';
import { linkRecording, unlinkRecording, ensureToday, todayKey } from '../state.js';
import { pageHead, sectionTitle, emptyState, statTile } from '../components.js';
import { icon } from '../icons.js';
import { $, $$, esc, toast, confirmDialog, formatClock, formatDate, formatBytes } from '../util.js';

export const recordingsView = {
  id: 'recordings',
  label: '錄音',
  title: '錄音庫',
  icon: 'mic',

  mount(root, params = []) {
    const recorder = new TakeRecorder();
    const urls = [];
    let list = [];
    let meterTimer = null;

    const objectURL = (blob) => {
      const url = URL.createObjectURL(blob);
      urls.push(url);
      return url;
    };

    const render = () => {
      const day = ensureToday();
      const totalSize = list.reduce((a, r) => a + (r.size || 0), 0);
      const groups = list.reduce((acc, rec) => {
        (acc[rec.dayKey] = acc[rec.dayKey] || []).push(rec);
        return acc;
      }, {});

      root.innerHTML = `
        ${pageHead('錄音庫', '不中斷錄音是唯一誠實的驗收方式。錄音存在裝置本機，不會上傳。')}

        <section class="card recorder">
          <div class="recorder__state">
            <div class="recorder__dot ${recorder.state === 'recording' ? 'is-live' : ''}"></div>
            <strong data-rec-time>${formatClock(recorder.elapsed)}</strong>
          </div>
          <div class="meter"><span data-meter style="width:0%"></span></div>
          <label class="field"><span class="field__label">這次要錄什麼</span>
            <input class="input" data-rec-title placeholder="例：Beethoven 第一樂章 展開部 不中斷" value="${esc(day.tasks.find((t) => !t.done)?.title || '')}">
          </label>
          <div class="row row--center" style="margin-top:12px">
            <button class="btn btn--big ${recorder.state === 'recording' ? 'btn--danger' : 'btn--primary'}" data-rec-toggle ${recorderSupported() ? '' : 'disabled'}>
              ${recorder.state === 'recording' ? `${icon('stop')}停止並儲存` : `${icon('record')}開始錄音`}
            </button>
          </div>
          ${recorderSupported() ? '' : '<p class="muted small" style="text-align:center;margin-top:10px">此瀏覽器不支援錄音。iPhone 請用 Safari 開啟。</p>'}
        </section>

        <div class="tiles">
          ${statTile('總 take 數', list.length, '存在本機')}
          ${statTile('今日 take', (groups[todayKey()] || []).length, formatDate(todayKey()))}
          ${statTile('佔用空間', formatBytes(totalSize), '瀏覽器儲存空間')}
        </div>

        ${sectionTitle('全部錄音')}
        <div class="stack">
          ${list.length ? Object.entries(groups).sort((a, b) => b[0].localeCompare(a[0])).map(([key, recs]) => `
            <div class="rec-group">
              <h3 class="rec-group__date">${esc(formatDate(key))}</h3>
              ${recs.map((r) => `
                <article class="card rec">
                  <div class="row row--between">
                    <div>
                      <strong>${esc(r.title)}</strong>
                      <p class="muted small">${formatClock(r.seconds)} · ${formatBytes(r.size)}</p>
                    </div>
                    <button class="icon-btn" data-del="${esc(r.id)}" aria-label="刪除">${icon('trash')}</button>
                  </div>
                  <audio controls preload="none" src="${objectURL(r.blob)}"></audio>
                  <div class="rec__rate">
                    ${[1, 2, 3, 4, 5].map((n) => `<button class="star ${r.rating >= n ? 'is-on' : ''}" data-rate="${esc(r.id)}:${n}" aria-label="評分 ${n}">${icon('star')}</button>`).join('')}
                    <input class="input input--sm" data-note="${esc(r.id)}" placeholder="這個 take 的 3 個問題…" value="${esc(r.note || '')}">
                  </div>
                </article>`).join('')}
            </div>`).join('')
            : emptyState('mic', '還沒有錄音', '今天就錄一次不重來的 take，明天才有東西可以比較。')}
        </div>`;

      bind();
    };

    const bind = () => {
      const toggle = $('[data-rec-toggle]', root);
      if (toggle) {
        toggle.addEventListener('click', async () => {
          if (recorder.state === 'recording') {
            const result = await recorder.stop();
            clearInterval(meterTimer);
            if (result && result.blob.size > 0) {
              const title = $('[data-rec-title]', root)?.value.trim();
              const record = await saveTake(result, { title: title || undefined, dayKey: todayKey() });
              linkRecording(record.id);
              toast('已儲存錄音', 'good');
            }
            await load();
            return;
          }
          try {
            await recorder.start((peak) => {
              const meter = $('[data-meter]', root);
              if (meter) meter.style.width = `${Math.min(100, peak * 140)}%`;
            });
            toggle.innerHTML = `${icon('stop')}停止並儲存`;
            toggle.classList.replace('btn--primary', 'btn--danger');
            $('.recorder__dot', root)?.classList.add('is-live');
            meterTimer = setInterval(() => {
              const t = $('[data-rec-time]', root);
              if (t) t.textContent = formatClock(recorder.elapsed);
            }, 250);
          } catch (err) {
            toast(err.message || '無法開始錄音', 'bad');
          }
        });
      }

      $$('[data-del]', root).forEach((btn) => btn.addEventListener('click', async () => {
        if (!await confirmDialog('刪除錄音', '刪掉之後就沒有了，確定嗎？', '刪除')) return;
        await recordingsDB.remove(btn.dataset.del);
        unlinkRecording(btn.dataset.del);
        await load();
        toast('已刪除');
      }));

      $$('[data-rate]', root).forEach((btn) => btn.addEventListener('click', async () => {
        const [id, n] = btn.dataset.rate.split(':');
        await recordingsDB.update(id, { rating: Number(n) });
        await load();
      }));

      $$('[data-note]', root).forEach((input) => input.addEventListener('change', async () => {
        await recordingsDB.update(input.dataset.note, { note: input.value });
        toast('已存下 take 筆記', 'good');
      }));
    };

    const load = async () => {
      try {
        list = await recordingsDB.all();
      } catch (err) {
        console.warn('[recordings] load failed', err);
        list = [];
      }
      render();
    };

    load().then(() => {
      if (params[0] === 'new' && recorderSupported()) {
        $('[data-rec-toggle]', root)?.focus();
        toast('按下「開始錄音」，錄完不要重來');
      }
    });

    return () => {
      clearInterval(meterTimer);
      recorder.cancel();
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  },
};
