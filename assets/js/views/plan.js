// LV.1 – LV.7 competition path with live gate progress.

import { stats } from '../state.js';
import { PHASES, phaseProgress, currentPhaseIndex } from '../content.js';
import { pageHead, progressBar } from '../components.js';
import { esc } from '../util.js';

export const planView = {
  id: 'plan',
  label: '任務線',
  title: '國際賽任務線',
  icon: 'path',

  mount(root) {
    const s = stats();
    const active = currentPhaseIndex(s);

    root.innerHTML = `
      ${pageHead('國際賽任務線', '從目前的技術重建，一路推進到國際賽決賽與奪牌窗口。')}
      <div class="quest-path">
        ${PHASES.map((p, i) => {
          const progress = phaseProgress(p, s);
          const stateClass = progress.complete ? 'is-clear' : (i === active ? 'is-current' : (i < active ? 'is-clear' : 'is-locked'));
          return `<article class="phase ${stateClass}">
            <div class="phase__rail"><span class="phase__dot">${progress.complete ? '✓' : (i === active ? '▶' : '')}</span></div>
            <div class="phase__body">
              <div class="row row--between">
                <div><span class="phase__lv">${esc(p.lv)}</span><h3>${esc(p.name)}</h3></div>
                <span class="muted small">${Math.round(progress.ratio * 100)}%</span>
              </div>
              <p class="muted">${esc(p.goal)}</p>
              ${progressBar(progress.ratio * 100, progress.complete ? 'good' : 'gold')}
              <ul class="checklist checklist--compact">
                ${progress.checks.map((c) => `<li class="${c.ok ? 'is-ok' : ''}"><span>${c.ok ? '✓' : '○'}</span>${esc(c.label)}</li>`).join('')}
              </ul>
            </div>
          </article>`;
        }).join('')}
      </div>
      <section class="card" style="margin-top:16px">
        <h3>怎麼用這條線</h3>
        <p class="muted">晉級條件是用你自己的能力面板分數、曲目成熟度與連勝天數算出來的。它不會幫你判斷實力，只保證你在往下一階推進之前，先把上一階的洞補完。</p>
      </section>`;
  },
};
