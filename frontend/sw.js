const CACHE_PREFIX = 'kingflow-pwa-';
const CACHE_NAME = `${CACHE_PREFIX}v76`;
const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/onboarding.html',
  '/client.html',
  '/client-account.html',
  '/signup.html',
  '/reset-password.html',
  '/admin.html',
  '/offline.html',
  '/manifest.webmanifest',
  '/css/styles.css',
  '/css/auth-pages.css',
  '/css/account-security.css',
  '/css/ui-feedback.css',
  '/css/client.css?v=20261125-booking-answers-2',
  '/css/client-account.css?v=20261125-style-passport-1',
  '/css/business-gallery.css?v=20261125-cover-preview-1',
  '/images/barbershop-hero.png',
  '/css/owner-dashboard.css?v=20261125-style-retention-1',
  '/js/main.js?v=20261125-style-retention-1',
  '/js/client-account.js?v=20261125-style-retention-1',
  '/js/security.js',
  '/js/config.js',
  '/js/auth.js',
  '/js/account-security.js',
  '/js/ui-feedback.js',
  '/js/signup.js',
  '/js/password-reset.js',
  '/js/admin.js',
  '/js/onboarding.js',
  '/js/offline.js',
  '/js/client.js?v=20261125-waitlist-1',
  '/js/pwa.js',
  '/icons/icon-192.svg',
  '/icons/icon-512.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS_TO_CACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    return;
  }

  const requestUrl = new URL(event.request.url);
  const isSameOrigin = requestUrl.origin === self.location.origin;

  if (!isSameOrigin) {
    return;
  }

  // Never put API payloads or authenticated responses in the shared offline cache.
  if (requestUrl.pathname.startsWith('/api/') ||
      requestUrl.pathname.startsWith('/uploads/private/') ||
      event.request.headers.has('Authorization')) {
    return;
  }

  // URLs with query strings can contain credentials or personalized data under
  // names the worker cannot predict. Do not persist them as cache keys or bodies.
  if (requestUrl.search) {
    event.respondWith(
      fetch(event.request).catch(() =>
        event.request.mode === 'navigate' ? caches.match('/offline.html') : Response.error()
      )
    );
    return;
  }

  const isNavigationRequest = event.request.mode === 'navigate';

  event.respondWith(
    (async () => {
      try {
        const networkResponse = await fetch(event.request);

        if (networkResponse && networkResponse.status === 200) {
          try {
            const responseClone = networkResponse.clone();
            const cache = await caches.open(CACHE_NAME);
            await cache.put(event.request, responseClone);
          } catch (_) {
            // A full or unavailable cache must not turn a successful network response into an error.
          }
        }

        return networkResponse;
      } catch (error) {
        const cachedResponse = await caches.match(event.request);
        if (cachedResponse) {
          return cachedResponse;
        }

        if (isNavigationRequest) {
          return caches.match('/offline.html');
        }

        return caches.match('/index.html');
      }
    })()
  );
});
