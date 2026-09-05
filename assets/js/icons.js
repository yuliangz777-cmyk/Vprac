// Hairline SVG icon set. Emoji read as a placeholder; a consistent 24px
// stroke set at 1.5 weight is what makes the chrome look drawn rather than typed.

const P = {
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.4"/><path d="M12 1.8v2.6M12 19.6v2.6M1.8 12h2.6M19.6 12h2.6"/>',
  metronome: '<path d="M9.4 3.6h5.2l4.1 16.8H5.3z"/><path d="M6.6 15.4h10.8"/><path d="M16.8 6.4 9.6 17.2"/>',
  radar: '<path d="M12 3.2 20 8v8l-8 4.8L4 16V8z"/><path d="M12 7.4 16.2 10v4.6L12 17l-4.2-2.4V10z"/>',
  book: '<path d="M4.4 4.6h6.2a2.4 2.4 0 0 1 2.4 2.4v12a2 2 0 0 0-2-2H4.4z"/><path d="M19.6 4.6h-6.2a2.4 2.4 0 0 0-2.4 2.4v12a2 2 0 0 1 2-2h6.6z"/>',
  check: '<path d="M4.6 12.4 9.4 17.2 19.4 6.8"/>',
  checkCircle: '<circle cx="12" cy="12" r="8.4"/><path d="M8.2 12.2 11 15l4.9-5.4"/>',
  path: '<path d="M6.5 20.4c0-3 4-3.2 4-6.2s-4-3.2-4-6.2a3 3 0 0 1 3-3"/><circle cx="6.5" cy="20.4" r="1.6"/><circle cx="17.5" cy="5" r="1.6"/><path d="M15.9 5H9.5"/>',
  trophy: '<path d="M7.4 4h9.2v5.2a4.6 4.6 0 0 1-9.2 0z"/><path d="M7.4 5.6H4.8v1.6a3 3 0 0 0 2.6 3M16.6 5.6h2.6v1.6a3 3 0 0 1-2.6 3"/><path d="M12 13.8v3.6M8.8 20.2h6.4"/>',
  calendar: '<rect x="3.6" y="5.4" width="16.8" height="15" rx="2.2"/><path d="M3.6 10.2h16.8M8.4 3.4v3.6M15.6 3.4v3.6"/>',
  mic: '<rect x="9.2" y="2.8" width="5.6" height="11.4" rx="2.8"/><path d="M5.6 11.6a6.4 6.4 0 0 0 12.8 0M12 18v3.2"/>',
  medal: '<circle cx="12" cy="14.6" r="5.6"/><path d="m8.6 9.2-3-6.4M15.4 9.2l3-6.4"/><path d="m12 12 .9 1.9 2 .3-1.5 1.4.4 2-1.8-1-1.8 1 .4-2-1.5-1.4 2-.3z"/>',
  settings: '<path d="M4.4 7.6h15.2M4.4 16.4h15.2"/><circle cx="9.4" cy="7.6" r="2.4"/><circle cx="15" cy="16.4" r="2.4"/>',
  more: '<circle cx="5.4" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="18.6" cy="12" r="1.5"/>',
  tone: '<path d="M9.4 18.2V5.6l9.2-2v12.6"/><circle cx="6.8" cy="18.2" r="2.6"/><circle cx="16" cy="16.2" r="2.6"/>',
  gauge: '<path d="M4 17.2a8.6 8.6 0 1 1 16 0"/><path d="m12 17.2 4.2-6"/><circle cx="12" cy="17.2" r="1.2"/>',
  clock: '<circle cx="12" cy="12" r="8.6"/><path d="M12 6.8V12l3.4 2.2"/>',
  flame: '<path d="M12 21.2c3.6 0 6-2.4 6-5.6 0-4.4-4.2-5.6-3.4-10.8-2.8 1-4.6 3.6-4.6 6 0 1.4-.7 2-1.6 2s-1.6-.8-1.6-2.4c-1.2 1.4-1.8 3.2-1.8 5.2 0 3.2 2.4 5.6 7 5.6z"/>',
  crown: '<path d="M4 8.4 7.6 13 12 5.6 16.4 13 20 8.4v9.2H4z"/>',
  star: '<path d="m12 3.8 2.6 5.5 5.8.8-4.2 4.2 1 6-5.2-2.9-5.2 2.9 1-6-4.2-4.2 5.8-.8z"/>',
  chart: '<path d="M4 20V9.6M10 20V4.4M16 20v-7.2M20.4 20H3.6"/>',
  sparkle: '<path d="m12 3.4 1.9 5.3 5.3 1.9-5.3 1.9L12 17.8l-1.9-5.3-5.3-1.9 5.3-1.9z"/><path d="M18.6 16.4l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
  pin: '<path d="M12 21.2s6.2-6 6.2-10.4a6.2 6.2 0 1 0-12.4 0C5.8 15.2 12 21.2 12 21.2z"/><circle cx="12" cy="10.6" r="2.4"/>',
  play: '<path d="M8 5.4 18.6 12 8 18.6z"/>',
  pause: '<path d="M9.2 5.4v13.2M14.8 5.4v13.2"/>',
  stop: '<rect x="6.4" y="6.4" width="11.2" height="11.2" rx="1.6"/>',
  record: '<circle cx="12" cy="12" r="5.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="8.6"/>',
  chevron: '<path d="m9.4 5.6 6.4 6.4-6.4 6.4"/>',
  chevronLeft: '<path d="M14.6 5.6 8.2 12l6.4 6.4"/>',
  close: '<path d="M6.2 6.2l11.6 11.6M17.8 6.2 6.2 17.8"/>',
  trash: '<path d="M4.8 6.6h14.4M9.6 6.6V4.4h4.8v2.2M6.8 6.6l1 13h8.4l1-13"/>',
  plus: '<path d="M12 5.2v13.6M5.2 12h13.6"/>',
  refresh: '<path d="M20 5.6v5h-5"/><path d="M19.4 10.6a7.6 7.6 0 1 0-1.2 6.6"/>',
  moon: '<path d="M20 13.8A8.4 8.4 0 0 1 10.2 4a8.4 8.4 0 1 0 9.8 9.8z"/>',
  note: '<path d="M9 18.4V5.2l9.4-2v13"/><circle cx="6.4" cy="18.4" r="2.6"/><circle cx="15.8" cy="16.2" r="2.6"/>',
  menu: '<path d="M4.4 7.4h15.2M4.4 12h15.2M4.4 16.6h15.2"/>',
  scroll: '<path d="M6.6 4.6h10.8v12.8a3 3 0 0 0 3 3H6.6a3 3 0 0 1-3-3V7.6a3 3 0 0 1 3-3z"/><path d="M9.6 8.8h5.4M9.6 12.4h5.4"/>',
};

/** Inline SVG string; inherits colour from the parent via currentColor. */
export function icon(name, size = 24) {
  const path = P[name] || P.sparkle;
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor"
    stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}

export const hasIcon = (name) => Object.hasOwn(P, name);

/** Gradient definition the progress ring references as url(#vqGold). */
export function goldGradientDefs() {
  return `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
    <linearGradient id="vqGold" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="var(--gold)"/>
      <stop offset="45%" stop-color="var(--gold-2)"/>
      <stop offset="100%" stop-color="var(--gold)"/>
    </linearGradient>
  </defs></svg>`;
}
