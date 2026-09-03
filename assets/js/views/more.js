// "More" hub: everything that does not fit in the five primary tabs.

import { state, stats } from '../state.js';
import { navigate } from '../router.js';
import { pageHead, statTile } from '../components.js';
import { $$, esc, formatMinutes, isIOS, isStandalone } from '../util.js';

const LINKS = [
  { id: 'plan', icon: '🗺️', label: '國際賽任務線', hint: 'LV.1 → LV.7 的晉級條件' },
  { id: 'competition', icon: '🏆', label: '比賽中心', hint: '倒數、目標與比賽紀錄' },
  { id: 'calendar', icon: '📅', label: '訓練日曆', hint: '每天練了多久、是否達標' },
  { id: 'recordings', icon: '🎙️', label: '錄音庫', hint: '不重來的 take 都放這裡' },
  { id: 'achievements', icon: '🏅', label: '成就', hint: '長期累積的證據' },
  { id: 'settings', icon: '⚙️', label: '設定與備份', hint: '個人資料、驗收標準、匯出' },
];

export const moreView = {
  id: 'more',
  label: '更多',
  title: '更多',
  icon: '⋯',
  primary: true,

  mount(root) {
    const s = stats();
    root.innerHTML = `
      ${pageHead('更多', `${esc(state.profile.name || '你')}的訓練檔案`)}
      <div class="tiles">
        ${statTile('等級', `LV.${s.level}`, `${s.xp} XP`)}
        ${statTile('累積練習', formatMinutes(s.totalMinutes), `${s.activeDays} 天`)}
        ${statTile('成就', `${state.achievements.length}`, '已解鎖')}
      </div>
      <nav class="menu">
        ${LINKS.map((l) => `<button class="menu__item" data-go="${l.id}">
          <span class="menu__icon">${l.icon}</span>
          <span class="menu__text"><strong>${esc(l.label)}</strong><small>${esc(l.hint)}</small></span>
          <span class="menu__chev">›</span>
        </button>`).join('')}
      </nav>
      ${isIOS() && !isStandalone() ? `
        <section class="card install-hint">
          <h3>把它變成 App</h3>
          <ol class="muted">
            <li>在 Safari 按下方的「分享」按鈕</li>
            <li>選「加入主畫面」</li>
            <li>從主畫面打開，就會全螢幕、可離線使用</li>
          </ol>
        </section>` : ''}`;

    $$('[data-go]', root).forEach((btn) => btn.addEventListener('click', () => navigate(btn.dataset.go)));
  },
};
