// Hash router. Hash routing keeps the back gesture working inside an iOS
// standalone web app and survives being launched from the Home Screen.

const routes = new Map();
let current = null;
let cleanup = null;
let onChange = null;

export function register(route) {
  routes.set(route.id, route);
}

export function registerAll(list) {
  list.forEach(register);
}

export function routeList() {
  return Array.from(routes.values());
}

export function currentRoute() {
  return current;
}

export function parseHash() {
  const raw = (location.hash || '').replace(/^#\/?/, '');
  const [id, ...rest] = raw.split('/');
  return { id: id || 'dashboard', params: rest };
}

export function navigate(id, params = []) {
  const next = `#/${[id, ...params].filter(Boolean).join('/')}`;
  if (location.hash === next) render();
  else location.hash = next;
}

export function onRouteChange(fn) { onChange = fn; }

export function render() {
  const { id, params } = parseHash();
  const route = routes.get(id) || routes.get('dashboard');
  if (!route) return;

  if (cleanup) { try { cleanup(); } catch (err) { console.warn('[router] cleanup', err); } }
  cleanup = null;
  current = route;

  const outlet = document.getElementById('view');
  outlet.innerHTML = '';
  outlet.dataset.route = route.id;
  const result = route.mount(outlet, params);
  if (typeof result === 'function') cleanup = result;

  document.title = route.title ? `${route.title} · Violin Quest Pro` : 'Violin Quest Pro';
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  if (onChange) onChange(route);
}

/** Re-render the active route in place (used after state changes). */
export function refresh() {
  if (current) render();
}

export function start() {
  window.addEventListener('hashchange', render);
  if (!location.hash) location.replace('#/dashboard');
  render();
}
