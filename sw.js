// dijital hisse PWA v8: HER ZAMAN once ag (network-first), ag yoksa onbellek. Eski sayfa kopyasi asla once sunulmaz.
const K = "dh-v8";
const KABUK = ["./", "./index.html", "./manifest.json", "./icon.svg", "./icon-192.png", "./icon-512.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(K).then(c => c.addAll(KABUK)).catch(() => {})); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== K).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(
    fetch(e.request, { cache: "no-store" }).then(x => { caches.open(K).then(c => c.put(e.request, x.clone())); return x; })
      .catch(() => caches.match(e.request, { ignoreSearch: true }))
  );
});
