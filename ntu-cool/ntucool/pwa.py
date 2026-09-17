"""讓本機網頁介面可以「加到主畫面」：manifest 與 Service Worker。

離線能做什麼：介面本身與**上一次的資料**（近期作業、成績、檔案清單）會被快取，
所以沒網路也打得開、看得到。要抓新資料當然還是得連得上 NTU COOL。

注意：Service Worker 需要安全來源。`http://127.0.0.1` 算安全，
但用區網 IP（`http://192.168.x.x`）開就不算，那種情況下離線功能會自動停用。
"""

from __future__ import annotations

import json

THEME_COLOR = "#0b62d6"
BACKGROUND_COLOR = "#f6f6f7"


def manifest(key: str) -> str:
    """start_url 帶著存取金鑰，從主畫面點開才不會又被擋在門外。"""
    return json.dumps(
        {
            "name": "NTU COOL 同步",
            "short_name": "NTU COOL",
            "description": "自動擷取 NTU COOL 課程檔案、作業截止日與成績",
            "lang": "zh-Hant",
            "start_url": f"/?k={key}",
            "scope": "/",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": BACKGROUND_COLOR,
            "theme_color": THEME_COLOR,
            "icons": [
                {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": "/icon-512-maskable.png", "sizes": "512x512", "type": "image/png",
                 "purpose": "maskable"},
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


#: 換版本號就會讓舊快取被清掉
CACHE_VERSION = "v1"

SERVICE_WORKER = """\
const SHELL = 'ntucool-shell-%(version)s';
const DATA = 'ntucool-data-%(version)s';
const SHELL_URLS = ['/icon-192.png', '/icon-512.png'];

// 這些不該被快取：檔案下載很大，進度與同步必須是即時的
const NEVER_CACHE = ['/files/', '/api/progress', '/api/sync', '/api/login', '/api/logout'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL).then(cache => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== SHELL && k !== DATA).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;
  if (NEVER_CACHE.some(prefix => url.pathname.startsWith(prefix))) return;
  event.respondWith(networkFirst(request, url.pathname.startsWith('/api/') ? DATA : SHELL));
});

// 有網路就用新的，順便存起來；沒網路就拿上次存的
async function networkFirst(request, cacheName){
  try{
    const response = await fetch(request);
    if(response && response.ok){
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  }catch(error){
    const cached = await caches.match(request);
    if(cached) return cached;
    if(request.mode === 'navigate'){
      const shell = await caches.match(request, {ignoreSearch: true});
      if(shell) return shell;
    }
    throw error;
  }
}
""" % {"version": CACHE_VERSION}
