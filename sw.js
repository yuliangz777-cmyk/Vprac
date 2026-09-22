/* Violin Quest Pro service worker.
 * Bump CACHE_VERSION together with APP_VERSION in assets/js/version.js. */

const CACHE_VERSION = '1.1.0';
const CACHE_NAME = `violin-quest-${CACHE_VERSION}`;

const PRECACHE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './assets/css/app.css',
  './assets/css/fonts.css',
  './assets/fonts/jost-latin.woff2',
  './assets/fonts/jost-latin-ext.woff2',
  './assets/fonts/cormorant-latin.woff2',
  './assets/fonts/cormorant-latin-ext.woff2',
  './assets/fonts/marcellus-latin.woff2',
  './assets/fonts/marcellus-latin-ext.woff2',
  './assets/js/main.js',
  './assets/js/util.js',
  './assets/js/icons.js',
  './assets/js/state.js',
  './assets/js/content.js',
  './assets/js/components.js',
  './assets/js/router.js',
  './assets/js/audio.js',
  './assets/js/db.js',
  './assets/js/recorder.js',
  './assets/js/session.js',
  './assets/js/theme.js',
  './assets/js/version.js',
  './assets/js/views/dashboard.js',
  './assets/js/views/practice.js',
  './assets/js/views/skills.js',
  './assets/js/views/repertoire.js',
  './assets/js/views/review.js',
  './assets/js/views/plan.js',
  './assets/js/views/competition.js',
  './assets/js/views/calendar.js',
  './assets/js/views/recordings.js',
  './assets/js/views/achievements.js',
  './assets/js/views/settings.js',
  './assets/js/views/more.js',
  './icons/favicon.png',
  './icons/apple-touch-icon.png',
  './icons/icon-192.png',
  './icons/icon-256.png',
  './icons/icon-512.png',
  './icons/maskable-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      // addAll() rejects the whole install if a single file 404s; adding them
      // individually keeps the app installable even if one asset is missing.
      .then((cache) => Promise.all(PRECACHE.map((url) => cache.add(url).catch((err) => {
        console.warn('[sw] precache skipped', url, err);
      }))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Navigations: network first so a deployed update is picked up promptly,
  // falling back to the cached shell when offline.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put('./index.html', copy));
          return response;
        })
        .catch(() => caches.match('./index.html').then((cached) => cached || caches.match('./'))),
    );
    return;
  }

  // Everything else: cache first, revalidating in the background.
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type === 'basic') {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    }),
  );
});
