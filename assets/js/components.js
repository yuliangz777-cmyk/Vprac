// Reusable presentational fragments. Everything returns an HTML string so the
// views stay simple template functions; interactivity is wired via delegation.

import { esc, pct, formatMinutes } from './util.js';
import { SKILL_LABELS } from './content.js';

export function pageHead(title, subtitle, right = '') {
  return `<header class="page-head">
    <div><h1>${esc(title)}</h1><p class="muted">${esc(subtitle)}</p></div>
    ${right ? `<div class="page-head__right">${right}</div>` : ''}
  </header>`;
}

export function statPills(stats) {
  return `<div class="pills">
    <span class="pill"><b>LV.${stats.level}</b> 等級</span>
    <span class="pill"><b>${stats.xp}</b> XP</span>
    <span class="pill pill--flame"><b>${stats.streak}</b> 天連勝</span>
  </div>`;
}

export function card(inner, className = '') {
  return `<section class="card ${className}">${inner}</section>`;
}

export function statTile(label, value, sub = '', tone = '') {
  return `<div class="tile ${tone ? `tile--${tone}` : ''}">
    <span class="tile__label">${esc(label)}</span>
    <strong class="tile__value">${esc(value)}</strong>
    ${sub ? `<span class="tile__sub">${esc(sub)}</span>` : ''}
  </div>`;
}

/** Circular progress ring (SVG, theme-aware via currentColor tokens). */
export function ring(percent, centerTop, centerBottom = '', size = 128) {
  const p = pct(percent);
  const r = size / 2 - 9;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - p / 100);
  return `<div class="ring" style="--ring-size:${size}px">
    <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">
      <circle class="ring__track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="10"/>
      <circle class="ring__value" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="10"
        stroke-linecap="round" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${offset.toFixed(1)}"
        transform="rotate(-90 ${size / 2} ${size / 2})"/>
    </svg>
    <div class="ring__label"><strong>${esc(centerTop)}</strong>${centerBottom ? `<span>${esc(centerBottom)}</span>` : ''}</div>
  </div>`;
}

export function progressBar(percent, tone = '') {
  return `<div class="bar ${tone ? `bar--${tone}` : ''}"><span style="width:${pct(percent)}%"></span></div>`;
}

/** Radar chart of the eight ability scores. */
export function skillRadar(skills, size = 260) {
  const keys = Object.keys(skills);
  const n = keys.length;
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 40;
  const padX = 52; // room for the left/right axis labels outside the polygon
  const point = (i, value) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const r = (radius * Math.max(4, value)) / 100;
    return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
  };
  const rings = [25, 50, 75, 100].map((level) => {
    const pts = keys.map((_, i) => point(i, level).map((v) => v.toFixed(1)).join(',')).join(' ');
    return `<polygon class="radar__grid" points="${pts}"/>`;
  }).join('');
  const axes = keys.map((_, i) => {
    const [x, y] = point(i, 100);
    return `<line class="radar__axis" x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`;
  }).join('');
  const shape = keys.map((k, i) => point(i, skills[k]).map((v) => v.toFixed(1)).join(',')).join(' ');
  const dots = keys.map((k, i) => {
    const [x, y] = point(i, skills[k]);
    return `<circle class="radar__dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3"/>`;
  }).join('');
  const labels = keys.map((k, i) => {
    const [x, y] = point(i, 118);
    const anchor = Math.abs(x - cx) < 12 ? 'middle' : (x > cx ? 'start' : 'end');
    const dx = anchor === 'start' ? 4 : (anchor === 'end' ? -4 : 0);
    return `<text class="radar__label" x="${(x + dx).toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${anchor}">${esc(SKILL_LABELS[k] || k)}</text>`;
  }).join('');
  return `<svg class="radar" viewBox="${-padX} -6 ${size + padX * 2} ${size + 12}" role="img" aria-label="能力面板雷達圖">
    ${rings}${axes}
    <polygon class="radar__shape" points="${shape}"/>
    ${dots}${labels}
  </svg>`;
}

/** Compact bar chart of daily minutes. */
export function minutesChart(series, goal = 0) {
  const max = Math.max(goal, ...series.map((d) => d.minutes), 30);
  const bars = series.map((d) => {
    const h = Math.round((d.minutes / max) * 100);
    const day = Number(d.key.slice(8));
    return `<div class="chart__col" title="${esc(d.key)}：${d.minutes} 分鐘">
      <div class="chart__bar ${d.minutes >= goal && goal ? 'is-goal' : ''}" style="height:${Math.max(3, h)}%"></div>
      <span>${day}</span>
    </div>`;
  }).join('');
  const goalLine = goal ? `<div class="chart__goal" style="bottom:${Math.round((goal / max) * 100)}%"><span>${goal} 分</span></div>` : '';
  return `<div class="chart">${goalLine}<div class="chart__cols">${bars}</div></div>`;
}

export function emptyState(icon, title, hint = '') {
  return `<div class="empty"><div class="empty__icon">${icon}</div><strong>${esc(title)}</strong>${hint ? `<p class="muted">${esc(hint)}</p>` : ''}</div>`;
}

export function field(label, control, hint = '') {
  return `<label class="field"><span class="field__label">${esc(label)}</span>${control}${hint ? `<span class="field__hint">${esc(hint)}</span>` : ''}</label>`;
}

export function sectionTitle(title, actionHTML = '') {
  return `<div class="section-title"><h2>${esc(title)}</h2>${actionHTML}</div>`;
}

export const minutesLabel = formatMinutes;
