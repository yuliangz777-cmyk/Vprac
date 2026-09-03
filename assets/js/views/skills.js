// Ability panel: radar chart, sliders, weekly snapshots and gate progress.

import { state, stats, setSkill, snapshotSkills } from '../state.js';
import { SKILL_KEYS, skillLabel, PHASES, currentPhaseIndex, phaseProgress } from '../content.js';
import { pageHead, card, sectionTitle, skillRadar, progressBar, emptyState } from '../components.js';
import { $$, esc, toast, formatDate } from '../util.js';

function trend(history, key) {
  if (history.length < 2) return 0;
  const last = history[history.length - 1].skills[key] ?? 0;
  const prev = history[history.length - 2].skills[key] ?? 0;
  return last - prev;
}

export const skillsView = {
  id: 'skills',
  label: '能力',
  title: '能力面板',
  icon: '📊',
  primary: true,

  mount(root) {
    const render = () => {
      const s = stats();
      const idx = currentPhaseIndex(s);
      const phase = PHASES[idx];
      const progress = phaseProgress(phase, s);
      const history = state.skillHistory;

      root.innerHTML = `
        ${pageHead('能力面板', '每週更新一次。分數最低的項目會提高隔天被派發的權重。')}

        <div class="split">
          ${card(`<div class="radar-wrap">${skillRadar(state.skills)}</div>
            <div class="row row--between" style="margin-top:6px">
              <span class="muted small">平均 ${s.avgSkill.toFixed(1)}</span>
              <span class="muted small">最低 ${s.minSkill}</span>
            </div>`)}
          ${card(`
            <h3>${esc(phase.lv)} ${esc(phase.name)} 晉級條件</h3>
            <p class="muted small">${esc(phase.goal)}</p>
            ${progressBar(progress.ratio * 100, 'gold')}
            <ul class="checklist">
              ${progress.checks.map((c) => `<li class="${c.ok ? 'is-ok' : ''}"><span>${c.ok ? '✓' : '○'}</span>${esc(c.label)}</li>`).join('')}
            </ul>`)}
        </div>

        ${sectionTitle('八項能力', '<button class="btn btn--sm btn--ghost" data-snapshot>存本週快照</button>')}
        <section class="card">
          ${SKILL_KEYS.map((k) => {
            const v = state.skills[k];
            const t = trend(history, k);
            return `<div class="skill-row">
              <span class="skill-row__name">${esc(skillLabel(k))}${t ? `<i class="delta ${t > 0 ? 'up' : 'down'}">${t > 0 ? '▲' : '▼'}${Math.abs(t)}</i>` : ''}</span>
              <input class="slider" type="range" min="0" max="100" value="${v}" data-skill="${k}">
              <output data-skill-out="${k}">${v}</output>
            </div>`;
          }).join('')}
          <p class="muted small">誠實打分比打高分有用：這裡的分數只影響系統怎麼幫你排任務。</p>
        </section>

        ${sectionTitle('快照紀錄')}
        <section class="card">
          ${history.length
            ? `<div class="history">${history.slice().reverse().slice(0, 12).map((h) => `
                <div class="history__row">
                  <strong>${esc(formatDate(h.date))}</strong>
                  <div class="history__bars">
                    ${SKILL_KEYS.map((k) => `<i title="${esc(skillLabel(k))} ${h.skills[k]}" style="height:${Math.max(4, h.skills[k])}%"></i>`).join('')}
                  </div>
                </div>`).join('')}</div>`
            : emptyState('📈', '還沒有快照', '每週按一次「存本週快照」，就能看到能力曲線。')}
        </section>`;

      $$('[data-skill]', root).forEach((input) => {
        const out = root.querySelector(`[data-skill-out="${input.dataset.skill}"]`);
        input.addEventListener('input', () => { out.textContent = input.value; });
        input.addEventListener('change', () => setSkill(input.dataset.skill, input.value));
      });
      $$('[data-snapshot]', root).forEach((btn) => btn.addEventListener('click', () => {
        snapshotSkills();
        toast('已存下本週能力快照', 'good');
        render();
      }));
    };

    render();
  },
};
