// Palette handling. Each palette is a complete warm "look" rather than a
// light/dark pair; `auto` follows the system by pairing the light and dark
// flagship palettes.

export const PALETTES = [
  {
    id: 'champagne',
    name: '香檳象牙',
    latin: 'Champagne Ivory',
    hint: '暖象牙底 × 古典金 × 咖啡棕字',
    mode: 'light',
    meta: '#f6f1e8',
    swatch: ['#f6f1e8', '#cfa74f', '#a5682a', '#2a2118'],
  },
  {
    id: 'amber-noir',
    name: '琥珀夜',
    latin: 'Amber Noir',
    hint: '濃縮咖啡黑 × 拉絲金 × 象牙白字',
    mode: 'dark',
    meta: '#100e0b',
    swatch: ['#100e0b', '#d3ad63', '#f0d59b', '#f3ece0'],
  },
  {
    id: 'burgundy',
    name: '勃根地',
    latin: 'Burgundy Velvet',
    hint: '深酒紅絨 × 金箔 × 奶油白字',
    mode: 'dark',
    meta: '#170a0e',
    swatch: ['#170a0e', '#a8384a', '#d6ab63', '#f7ebe6'],
  },
  {
    id: 'terracotta',
    name: '赤陶',
    latin: 'Terracotta Sun',
    hint: '暖沙底 × 赤陶橘 × 青銅金',
    mode: 'light',
    meta: '#fbf3ea',
    swatch: ['#fbf3ea', '#bd5323', '#d9a24a', '#32231a'],
  },
];

export const PALETTE_IDS = PALETTES.map((p) => p.id);

const AUTO_LIGHT = 'champagne';
const AUTO_DARK = 'amber-noir';

const prefersDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches;

/** The palette actually painted right now (resolves `auto`). */
export function resolvePalette(mode = 'auto') {
  if (PALETTE_IDS.includes(mode)) return mode;
  return prefersDark() ? AUTO_DARK : AUTO_LIGHT;
}

export const paletteById = (id) => PALETTES.find((p) => p.id === id);

export function applyPalette(mode = 'auto') {
  const root = document.documentElement;
  if (mode === 'auto') root.removeAttribute('data-palette');
  else root.setAttribute('data-palette', mode);

  const active = paletteById(resolvePalette(mode));
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.remove());
  const meta = document.createElement('meta');
  meta.name = 'theme-color';
  meta.content = active?.meta || '#f6f1e8';
  document.head.appendChild(meta);

  // iOS uses this to decide the status-bar text colour in standalone mode.
  const bar = document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]');
  if (bar) bar.content = active?.mode === 'dark' ? 'black-translucent' : 'default';
}

export const TYPEFACES = [
  { id: 'serif', name: '宋體標題', hint: '雜誌感、最有質感' },
  { id: 'sans', name: '黑體標題', hint: '現代、銳利' },
];

/** Switches only the Chinese half of the display stack; Latin stays Cormorant. */
export function applyTypeface(mode = 'serif') {
  const root = document.documentElement;
  if (mode === 'sans') root.setAttribute('data-typeface', 'sans');
  else root.removeAttribute('data-typeface');
}

export function watchSystemTheme(getMode) {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = () => { if (getMode() === 'auto') applyPalette('auto'); };
  if (mq.addEventListener) mq.addEventListener('change', handler);
  else mq.addListener(handler);
}

// Backwards-compatible alias: earlier builds called this applyTheme.
export const applyTheme = applyPalette;
