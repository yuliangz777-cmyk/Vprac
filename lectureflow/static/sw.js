/* LectureFlow service worker.
 * Bump CACHE_VERSION whenever the precache list or any shell asset changes. */

const CACHE_VERSION = '2.1.0';
const CACHE_NAME = `lectureflow-${CACHE_VERSION}`;

const PRECACHE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './styles.css',
  './app.js',
  './audio.js',
  './text.js',
  './engines.js',
  './prompts.js',
  './settings.js',
  './capture-worklet.js',
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
      // one at a time keeps the app installable even if one asset is missing.
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

  // Only ever touch same-origin GETs. Transcription and model calls are POSTs,
  // and with a stored key they go straight to the provider's origin - none of
  // that may be cached or replayed.
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // The backend's own endpoints are live state, never a cache hit.
  if (url.pathname.includes('/api/')) return;

  // Navigations: network first so a deployed update lands promptly, falling
  // back to the cached shell when offline.
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
