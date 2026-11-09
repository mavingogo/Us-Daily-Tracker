/* Us, Daily service worker: makes pages open offline.
   Pages: network first, fall back to the last saved copy. Static files: cached copy first, refreshed in background. */
const V = 'us-daily-v2';
const PRE = ['/offline', '/static/app.js', '/static/manifest.json', '/static/icon-192.png', '/static/icon-512.png'];
const NO_CACHE = /^\/(login|register|pair|logout)/;

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(V).then((c) => c.addAll(PRE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== V).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// The page tells us to wipe saved pages when someone signs out.
self.addEventListener('message', (e) => {
  if (e.data === 'clear') {
    e.waitUntil(caches.keys().then((ks) => Promise.all(ks.map((k) => caches.delete(k)))));
  }
});

self.addEventListener('fetch', (e) => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.origin !== location.origin) return;

  if (u.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.open(V).then((c) =>
        c.match(r).then((hit) => {
          const net = fetch(r).then((res) => { if (res.ok) c.put(r, res.clone()); return res; }).catch(() => hit);
          return hit || net;
        })
      )
    );
    return;
  }

  if (r.mode === 'navigate') {
    e.respondWith(
      fetch(r)
        .then((res) => {
          // Only save normal pages (not redirects to the login screen, not sign-in pages).
          if (res.ok && !res.redirected && !NO_CACHE.test(u.pathname)) {
            const copy = res.clone();
            caches.open(V).then((c) => c.put(r, copy));
          }
          return res;
        })
        .catch(() => caches.match(r).then((hit) => hit || caches.match('/offline')))
    );
  }
});
