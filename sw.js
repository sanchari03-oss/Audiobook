const CACHE_NAME = 'ssk-player-gh-v2';

const STATIC_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './books.json'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // Audio files / Range requests: Never cache in SW; let browser and IndexedDB handle directly
  if (e.request.destination === 'audio' || /\.(mp3|m4a|aac|ogg|wav)($|\?)/i.test(url.pathname)) {
    return;
  }

  // Navigate mode (HTML entry): Network first, fallback to cached index.html
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
          }
          return res;
        })
        .catch(async () => {
          return (await caches.match('./index.html')) || 
                 (await caches.match('./')) || 
                 (await caches.match(e.request));
        })
    );
    return;
  }

  // books.json and manifest.json: Network first, fallback to cache
  if (url.pathname.endsWith('/books.json') || url.pathname.endsWith('/manifest.json')) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
          }
          return res;
        })
        .catch(async () => {
          return (await caches.match(e.request, { ignoreSearch: true })) ||
                 (await caches.match('./books.json')) ||
                 new Response('{"books":[]}', { headers: { 'Content-Type': 'application/json' } });
        })
    );
    return;
  }

  // Static images, covers, icons: Cache first / Stale-while-revalidate
  if (/\.(jpg|jpeg|png|webp|svg|ico)($|\?)/i.test(url.pathname)) {
    e.respondWith(
      caches.match(e.request, { ignoreSearch: true }).then((cached) => {
        const fetchPromise = fetch(e.request)
          .then((networkRes) => {
            if (networkRes.ok) {
              const clone = networkRes.clone();
              caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
            }
            return networkRes;
          })
          .catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }
});
