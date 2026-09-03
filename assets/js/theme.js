// Theme handling: light / dark / follow-system, kept in sync with the iOS
// status bar colour so the standalone app does not flash the wrong shade.

const META_LIGHT = '#f4f6f8';
const META_DARK = '#12161c';

export function applyTheme(mode = 'auto') {
  const root = document.documentElement;
  if (mode === 'auto') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', mode);

  const dark = mode === 'dark' || (mode === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.remove());
  const meta = document.createElement('meta');
  meta.name = 'theme-color';
  meta.content = dark ? META_DARK : META_LIGHT;
  document.head.appendChild(meta);
}

export function watchSystemTheme(getMode) {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = () => { if (getMode() === 'auto') applyTheme('auto'); };
  if (mq.addEventListener) mq.addEventListener('change', handler);
  else mq.addListener(handler);
}
