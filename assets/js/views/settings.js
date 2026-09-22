// Settings: profile, plan size, acceptance criteria, backup and reset.

import {
  state, setProfile, setSetting, exportJSON, importJSON, resetState, saveNow, stats,
} from '../state.js';
import { recordingsDB } from '../db.js';
import { audio } from '../audio.js';
import { applyPalette, applyTypeface, PALETTES, TYPEFACES } from '../theme.js';
import { icon } from '../icons.js';
import { pageHead, sectionTitle, statTile } from '../components.js';
import { $, $$, esc, toast, confirmDialog, download, formatBytes, isIOS, isStandalone } from '../util.js';
import { APP_VERSION } from '../version.js';

export const settingsView = {
  id: 'settings',
  label: '設定',
  title: '設定',
  icon: 'settings',

  mount(root) {
    const render = async () => {
      const p = state.profile;
      const st = state.settings;
      const current = st.palette || st.theme || 'auto';
      const face = st.typeface || 'serif';
      const s = stats();
      const { usage, quota } = await recordingsDB.usage();

      root.innerHTML = `
        ${pageHead('設定', '調整每天可投入的時間、驗收標準與備份。')}

        <section class="card">
          <h3>個人</h3>
          <div class="grid-2">
            <label class="field"><span class="field__label">姓名</span><input class="input" data-p="name" value="${esc(p.name)}" placeholder="你的名字"></label>
            <label class="field"><span class="field__label">老師</span><input class="input" data-p="teacher" value="${esc(p.teacher || '')}"></label>
            <label class="field"><span class="field__label">目前主曲目</span><input class="input" data-p="mainWork" value="${esc(p.mainWork)}"></label>
            <label class="field"><span class="field__label">Cadenza</span><input class="input" data-p="cadenza" value="${esc(p.cadenza || '')}"></label>
            <label class="field"><span class="field__label">每日可練分鐘</span><input class="input" type="number" min="30" max="600" step="15" data-p="dailyMinutes" value="${p.dailyMinutes}"></label>
            <label class="field"><span class="field__label">每週練習天數</span><input class="input" type="number" min="1" max="7" data-p="weeklyDays" value="${p.weeklyDays}"></label>
          </div>
        </section>

        ${sectionTitle('色系')}
        <section class="card">
          <p class="muted small" style="margin-bottom:12px">四種暖色調配色，換了立刻生效。</p>
          <div class="palette-grid">
            ${[{ id: 'auto', name: '跟隨系統', latin: 'Automatic', hint: '白天香檳象牙，夜間琥珀夜', swatch: ['#f6f1e8', '#cfa74f', '#100e0b', '#d3ad63'] }, ...PALETTES].map((p) => `
              <button class="palette-card ${current === p.id ? 'is-on' : ''}" data-palette="${p.id}">
                <span class="palette-card__swatch">${p.swatch.map((c) => `<i style="background:${c}"></i>`).join('')}</span>
                <span class="palette-card__body">
                  ${current === p.id ? `<span class="palette-card__tick">${icon('check')}</span>` : ''}
                  <strong>${esc(p.name)}</strong>
                  <small>${esc(p.latin)} · ${esc(p.hint)}</small>
                </span>
              </button>`).join('')}
          </div>
        </section>

        ${sectionTitle('標題字體')}
        <section class="card">
          <p class="muted small" style="margin-bottom:12px">英文一律使用 Cormorant Garamond；這裡切換的是中文標題。</p>
          <div class="segmented">
            ${TYPEFACES.map((t) => `<button class="segmented__btn ${face === t.id ? 'is-on' : ''}" data-face="${t.id}">${esc(t.name)}</button>`).join('')}
          </div>
          <p class="muted small">${esc(TYPEFACES.find((t) => t.id === face)?.hint || '')}</p>
        </section>

        ${sectionTitle('音訊')}
        <section class="card">
          <label class="field"><span class="field__label">基準音 A4：<b data-a4-out>${st.a4}</b> Hz</span>
            <input class="slider" type="range" min="432" max="446" value="${st.a4}" data-s-range="a4">
          </label>
          <label class="switch"><input type="checkbox" data-s-check="autoPlan" ${st.autoPlan !== false ? 'checked' : ''}><span>每天自動產生任務菜單</span></label>
          <label class="switch"><input type="checkbox" data-s-check="keepAwake" ${st.keepAwake !== false ? 'checked' : ''}><span>計時中保持螢幕開啟</span></label>
        </section>

        ${sectionTitle('驗收標準')}
        <section class="card">
          <p class="muted small">這是每天／每週要通過的標準，可以改成你老師的要求。每行一項。</p>
          <label class="field"><span class="field__label">每日驗收</span><textarea class="input" rows="6" data-acc="daily">${esc(state.acceptance.daily.join('\n'))}</textarea></label>
          <label class="field"><span class="field__label">每週驗收</span><textarea class="input" rows="6" data-acc="weekly">${esc(state.acceptance.weekly.join('\n'))}</textarea></label>
          <div class="row row--end"><button class="btn btn--primary btn--sm" data-save-acc>儲存驗收標準</button></div>
        </section>

        ${sectionTitle('資料')}
        <div class="tiles">
          ${statTile('練習天數', s.activeDays, '有紀錄的日子')}
          ${statTile('錄音空間', formatBytes(usage), quota ? `可用 ${formatBytes(quota)}` : '瀏覽器估算')}
          ${statTile('版本', APP_VERSION, isStandalone() ? '已加入主畫面' : '瀏覽器分頁')}
        </div>
        <section class="card">
          <p class="muted small">所有資料只存在這台裝置的瀏覽器裡。換手機、清除 Safari 資料前，請先匯出備份。</p>
          <div class="row row--wrap">
            <button class="btn btn--primary btn--sm" data-export>匯出備份 JSON</button>
            <button class="btn btn--ghost btn--sm" data-import>匯入備份</button>
            <button class="btn btn--ghost btn--sm" data-clear-rec>清除所有錄音</button>
            <button class="btn btn--danger btn--sm" data-reset>重置所有資料</button>
          </div>
          <input type="file" accept="application/json,.json" hidden data-file>
        </section>

        ${sectionTitle('關於')}
        <section class="card">
          <p><strong>Violin Quest Pro</strong> ${esc(APP_VERSION)}</p>
          <p class="muted small">離線可用的小提琴訓練 App。${isIOS() && !isStandalone() ? '在 Safari 按「分享 → 加入主畫面」，就會像原生 App 一樣全螢幕開啟。' : ''}</p>
          <div class="row row--wrap" style="margin-top:10px">
            <button class="btn btn--ghost btn--sm" data-update>檢查更新</button>
          </div>
        </section>`;

      bind();
    };

    const bind = () => {
      $$('[data-p]', root).forEach((input) => input.addEventListener('change', () => {
        const key = input.dataset.p;
        const value = input.type === 'number' ? Number(input.value) : input.value.trim();
        setProfile({ [key]: value });
        toast('已儲存', 'good');
      }));

      $$('[data-face]', root).forEach((btn) => btn.addEventListener('click', () => {
        setSetting('typeface', btn.dataset.face);
        applyTypeface(btn.dataset.face);
        render();
      }));

      $$('[data-palette]', root).forEach((btn) => btn.addEventListener('click', () => {
        const id = btn.dataset.palette;
        setSetting('palette', id);
        applyPalette(id);
        render();
      }));

      const a4 = $('[data-s-range="a4"]', root);
      a4.addEventListener('input', () => { $('[data-a4-out]', root).textContent = a4.value; });
      a4.addEventListener('change', () => { setSetting('a4', Number(a4.value)); audio.a4 = Number(a4.value); });

      $$('[data-s-check]', root).forEach((box) => box.addEventListener('change', () => {
        setSetting(box.dataset.sCheck, box.checked);
      }));

      $('[data-save-acc]', root).addEventListener('click', () => {
        const parse = (sel) => $(`[data-acc="${sel}"]`, root).value.split('\n').map((l) => l.trim()).filter(Boolean);
        const daily = parse('daily');
        const weekly = parse('weekly');
        if (!daily.length || !weekly.length) { toast('每組至少要留一項', 'bad'); return; }
        state.acceptance = { daily, weekly };
        saveNow();
        toast('驗收標準已更新', 'good');
      });

      $('[data-export]', root).addEventListener('click', () => {
        download(`violin-quest-backup-${new Date().toISOString().slice(0, 10)}.json`, exportJSON());
        toast('備份已下載', 'good');
      });

      const file = $('[data-file]', root);
      $('[data-import]', root).addEventListener('click', () => file.click());
      file.addEventListener('change', async () => {
        const f = file.files?.[0];
        if (!f) return;
        try {
          const text = await f.text();
          if (!await confirmDialog('匯入備份', '匯入會覆蓋目前所有進度，確定嗎？', '覆蓋匯入')) return;
          importJSON(text);
          toast('匯入完成', 'good');
          render();
        } catch (err) {
          toast(err.message || '匯入失敗', 'bad');
        } finally {
          file.value = '';
        }
      });

      $('[data-clear-rec]', root).addEventListener('click', async () => {
        if (!await confirmDialog('清除錄音', '所有錄音都會被刪除，無法復原。', '全部刪除')) return;
        await recordingsDB.clear();
        toast('錄音已清除');
        render();
      });

      $('[data-reset]', root).addEventListener('click', async () => {
        if (!await confirmDialog('重置所有資料', '任務、能力、曲目、比賽紀錄全部歸零，建議先匯出備份。', '確定重置')) return;
        resetState();
        toast('已重置');
        location.hash = '#/dashboard';
      });

      $('[data-update]', root).addEventListener('click', async () => {
        if (!('serviceWorker' in navigator)) { toast('此瀏覽器不支援離線更新', 'bad'); return; }
        const reg = await navigator.serviceWorker.getRegistration();
        if (!reg) { toast('尚未啟用離線模式', 'bad'); return; }
        await reg.update();
        toast('已檢查更新，如有新版會提示重新載入');
      });
    };

    render();
  },
};
