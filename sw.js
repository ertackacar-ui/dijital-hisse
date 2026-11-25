// dijital hisse PWA: kabuk onbellekte, veri.json her zaman agdan.
const K = "dh-v7";
const KABUK = ["./", "./index.html", "./manifest.json", "./icon.svg", "./icon-192.png", "./icon-512.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(K).then(c => c.addAll(KABUK)).catch(() => {})); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== K).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (u.pathname.endsWith("veri.json") || u.pathname.endsWith("ozet_tr.json")) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(x => { if (u.origin === location.origin) caches.open(K).then(c => c.put(e.request, x.clone())); return x; })));
});
