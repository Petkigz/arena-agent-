// PWA service worker for the local dashboard application shell.
const CACHE_NAME = 'local-assistant-v3';

self.addEventListener('install', event => {
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys()
            .then(cacheNames => Promise.all(
                cacheNames
                    .filter(cacheName => cacheName !== CACHE_NAME)
                    .map(cacheName => caches.delete(cacheName))
            ))
            .then(() => self.clients.claim())
    );
});

function isCacheableAppShellRequest(request) {
    if (request.method !== 'GET') return false;

    const requestUrl = new URL(request.url);
    if (requestUrl.origin !== self.location.origin) return false;

    const isDashboardNavigation = request.mode === 'navigate' && requestUrl.pathname === '/';
    return isDashboardNavigation || requestUrl.pathname.startsWith('/static/');
}

self.addEventListener('fetch', event => {
    // API responses can contain memories, logs, rules, and system state. Never
    // place them in Cache Storage; authenticated APIs will rely on this boundary.
    if (!isCacheableAppShellRequest(event.request)) {
        event.respondWith(fetch(event.request));
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then(networkResponse => {
                if (networkResponse && networkResponse.ok) {
                    const responseToCache = networkResponse.clone();
                    event.waitUntil(
                        caches.open(CACHE_NAME)
                            .then(cache => cache.put(event.request, responseToCache))
                    );
                }
                return networkResponse;
            })
            .catch(() => caches.match(event.request))
    );
});
