// Service Worker for Candy Route Planner PWA
const CACHE_NAME = 'candy-route-v2';
const OFFLINE_URL = '/offline';

// Assets to cache on install (all local, no CDN)
const PRECACHE_ASSETS = [
    '/offline',
    '/static/css/app.css',
    '/static/js/app.js',
    '/static/js/offline.js',
    '/static/vendor/tailwind.js',
    '/static/vendor/htmx.min.js',
    '/static/vendor/alpine.min.js',
    '/static/manifest.json',
    '/static/icons/icon-192.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(PRECACHE_ASSETS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((names) => Promise.all(
                names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin) return;

    // API: network first, fall back to cache
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(networkFirst(event.request));
        return;
    }

    // Static assets: cache first
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(cacheFirst(event.request));
        return;
    }

    // HTML pages: network first, fall back to offline page
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
                }
                return response;
            })
            .catch(() => caches.match(event.request)
                .then((cached) => cached || caches.match(OFFLINE_URL))
            )
    );
});

async function cacheFirst(request) {
    const cached = await caches.match(request);
    if (cached) return cached;
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch (e) {
        return new Response('', { status: 503 });
    }
}

async function networkFirst(request) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch (e) {
        const cached = await caches.match(request);
        return cached || new Response('{"error":"offline"}', {
            status: 503, headers: { 'Content-Type': 'application/json' }
        });
    }
}

// Listen for skip waiting and cache route messages
self.addEventListener('message', (event) => {
    if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
    if (event.data?.type === 'CACHE_ROUTE') {
        caches.open(CACHE_NAME).then((c) => c.add('/api/route/today'));
    }
});

// Background sync
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-actions') {
        event.waitUntil(
            self.clients.matchAll().then((clients) =>
                clients.forEach((c) => c.postMessage({ type: 'SYNC_REQUESTED' }))
            )
        );
    }
});
