// Rinz Algo service worker: makes the dashboard installable and lets the app shell open without a network.
// It NEVER caches API data (prices, account, orders): those always come live from the backend.
const SHELL = "rinz-shell-v1";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(["/", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"])));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return; // API calls go straight to the network
  if (req.mode === "navigate") {
    // pages: network first, cached shell when offline
    e.respondWith(fetch(req).then((r) => { caches.open(SHELL).then((c) => c.put("/", r.clone())); return r; })
      .catch(() => caches.match("/")));
    return;
  }
  // built assets are content-hashed: cache first, then network
  e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((r) => {
    if (r.ok && url.pathname.startsWith("/assets/")) caches.open(SHELL).then((c) => c.put(req, r.clone()));
    return r;
  })));
});
