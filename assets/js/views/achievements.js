// Achievements: the long-run evidence that the habit is real.

import { state, stats } from '../state.js';
import { ACHIEVEMENTS } from '../content.js';
import { pageHead, statTile, progressBar } from '../components.js';
import { icon } from '../icons.js';
import { esc, formatMinutes } from '../util.js';

export const achievementsView = {
  id: 'achievements',
  label: '成就',
  title: '成就',
  icon: 'medal',

  mount(root) {
    const s = stats();
    const unlocked = new Set(state.achievements);

    root.innerHTML = `
      ${pageHead('成就', '這些數字沒辦法作弊：它們全部來自你實際記錄的練習。')}
      <div class="tiles">
        ${statTile('已解鎖', `${unlocked.size}/${ACHIEVEMENTS.length}`, '成就')}
        ${statTile('累積練習', formatMinutes(s.totalMinutes), `${s.activeDays} 天有練`)}
        ${statTile('完成任務', s.totalTasksDone, `Boss ${s.bossCount} 次`)}
        ${statTile('最佳連勝', `${s.bestStreak} 天`, `目前 ${s.streak} 天`)}
      </div>
      <section class="card" style="margin-top:14px">
        <div class="row row--between"><h3>整體進度</h3><span class="muted small">${Math.round((unlocked.size / ACHIEVEMENTS.length) * 100)}%</span></div>
        ${progressBar((unlocked.size / ACHIEVEMENTS.length) * 100, 'gold')}
      </section>
      <div class="badges">
        ${ACHIEVEMENTS.map((a) => `
          <article class="badge-card ${unlocked.has(a.id) ? 'is-on' : ''}">
            <div class="badge-card__icon">${icon(a.icon)}</div>
            <strong>${esc(a.name)}</strong>
            <p class="muted small">${esc(a.desc)}</p>
          </article>`).join('')}
      </div>`;
  },
};
