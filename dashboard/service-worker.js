/* ============================================================
   OA Detection System — Service Worker (PWA)
   SIH 2026 | PS-26004 | MDoNER
   - Cache-first for static assets
   - Network-first for API calls
   - Offline fallback with cached readings
   - Push notification support for high-risk alerts
   ============================================================ */

const CACHE_NAME    = 'oadetect-v2.0.0';
const API_CACHE     = 'oadetect-api-v1';

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/style.css',
  '/app.js',
  '/manifest.json',
  '/icon-192.png',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&family=Outfit:wght@400;600;700;800&display=swap',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js',
];

// ── INSTALL ────────────────────────────────────────────────────
self.addEventListener('install', event => {
  console.log('[SW] Installing OA Detect v2.0.0…');
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS.filter(url => !url.startsWith('http')));
    }).then(() => self.skipWaiting())
  );
});

// ── ACTIVATE ───────────────────────────────────────────────────
self.addEventListener('activate', event => {
  console.log('[SW] Activating…');
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME && k !== API_CACHE)
            .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── FETCH STRATEGY ─────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Skip WebSocket and Socket.IO requests
  if (url.pathname.startsWith('/socket.io') ||
      event.request.headers.get('upgrade') === 'websocket') {
    return;
  }

  // API calls: Network-first, cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstWithCache(event.request));
    return;
  }

  // Static assets: Cache-first, network fallback
  event.respondWith(cacheFirstWithNetwork(event.request));
});

async function cacheFirstWithNetwork(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response && response.status === 200) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response(
      '<html><body style="background:#030712;color:#22d3ee;font-family:sans-serif;text-align:center;padding:20%">' +
      '<h1>📡 OA Detect — Offline</h1><p>You are offline. Live data is unavailable.<br>Cached readings are still accessible.</p></body></html>',
      { headers: { 'Content-Type': 'text/html' } }
    );
  }
}

async function networkFirstWithCache(request) {
  try {
    const response = await fetch(request);
    if (response && response.status === 200) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(
      JSON.stringify({ status: 'offline', error: 'No network connection', cached: true }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  }
}

// ── PUSH NOTIFICATIONS ─────────────────────────────────────────
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  const title   = data.title   || '⚠️ OA Risk Alert';
  const body    = data.body    || 'High OA risk detected for a patient.';
  const patient = data.patient || '';

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon:   '/icon-192.png',
      badge:  '/icon-192.png',
      tag:    `oa-alert-${patient}`,
      renotify: true,
      vibrate: [200, 100, 200],
      data: { url: `/?tab=monitor&patient=${patient}` },
      actions: [
        { action: 'view',    title: 'View Dashboard' },
        { action: 'dismiss', title: 'Dismiss' },
      ]
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'view') {
    event.waitUntil(
      clients.openWindow(event.notification.data?.url || '/')
    );
  }
});
