// dijital hisse PWA v10: once ag (network-first); ag 4 sn icinde cevap vermezse veya yoksa onbellek. Eski sayfa kopyasi asla once sunulmaz.
const K = "dh-v10", BEKLE_MS = 4000;
const KABUK = ["./", "./index.html", "./manifest.json", "./icon.svg", "./icon-192.png", "./icon-512.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(K).then(c => c.addAll(KABUK)).catch(() => {})); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== K).map(k => caches.delete(k))))); self.clients.claim(); });
const anahtar = req => { const u = new URL(req.url); u.search = ""; return u.href; }; // veri.json?t=... tek kayitta tutulur
const onbellek = req => caches.match(anahtar(req), { ignoreSearch: true });
function agVeyaOnbellek(req) {
  return new Promise(res => {
    let bitti = false; const ver = x => { if (!bitti && x) { bitti = true; res(x); } };
    const sayac = setTimeout(() => onbellek(req).then(ver), BEKLE_MS); // ag gecikirse eldeki kopya, ag gelince yine de onbellege yazilir
    fetch(req, { cache: "no-store" })
      .then(x => { clearTimeout(sayac); const kopya = x.ok ? x.clone() : null; ver(x); if (kopya) caches.open(K).then(c => c.put(anahtar(req), kopya)); }) // klon, sayfa govdeyi okumaya baslamadan once alinir
      .catch(() => { clearTimeout(sayac); onbellek(req).then(c => ver(c || Response.error())); });
  });
}
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(agVeyaOnbellek(e.request));
});
