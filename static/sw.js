// Service Worker minimal : network-first, repli hors-ligne sur la page d'accueil en cache.
const CACHE = 'resida-v2';
const ASSETS = ['/'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;               // ne jamais mettre en cache les POST
  // Laisse passer les requêtes cross-origin (CDN Tailwind, Google Fonts, etc.)
  // sans les intercepter : le navigateur les gère normalement.
  if (new URL(e.request.url).origin !== self.location.origin) return;
  e.respondWith(
    fetch(e.request).catch(() =>
      caches.match(e.request).then(r => r || caches.match('/')))
  );
});
