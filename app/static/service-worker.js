// PWA Service Worker for Local Personal Assistant Standalone App
const CACHE_NAME = 'local-assistant-v1';
const ASSETS_TO_CACHE = [
    '/',
    '/static/index.html',
    '/static/manifest.json'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
});

self.addEventListener('fetch', event => {
    event.respondWith(
        fetch(event.request).catch(() => {
            return caches.match(event.request);
        })
    );
});
