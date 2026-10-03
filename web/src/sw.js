// Offline support: precache the whole site once, then serve it from the cache.
//
// `make web-build` stamps VERSION and FILES. The version is a hash of the
// content, so any change to the site changes this file's bytes, which is what
// makes the browser install a new worker; the old cache is removed when the
// new worker takes over.

const VERSION = "__VERSION__";
const FILES = __FILES__;

const CACHE = `dtcalc-${VERSION}`;
// The page the site address without a file name falls back to; build lists it.
const PAGE = "index.html";

self.addEventListener("install", (event) => {
  // `reload` skips the HTTP cache, so a precache never captures stale files.
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      cache.addAll(FILES.map((file) => new Request(file, { cache: "reload" }))),
    ),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names.filter((name) => name.startsWith("dtcalc-") && name !== CACHE).map((name) => caches.delete(name)),
        ),
      ),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" || new URL(request.url).origin !== location.origin) return;

  event.respondWith(
    // `?q=` links are the same page, so the query string is ignored.
    caches.match(request, { cacheName: CACHE, ignoreSearch: true }).then((hit) => {
      if (hit) return hit;
      if (request.mode === "navigate") {
        // The site address without a file name.
        return caches.match(PAGE, { cacheName: CACHE }).then((page) => page ?? fetch(request));
      }
      return fetch(request);
    }),
  );
});
