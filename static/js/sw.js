/* 知迹 Service Worker：静态资源缓存优先，页面走网络优先并带回退 */
const VERSION = "zhiji-shell-v2";
const PRECACHE = [
  "/offline/",
  "/static/css/app.css?v=4",
  "/static/js/app.js?v=4",
  "/static/js/editor.js?v=1",
  "/static/js/focus.js?v=1",
  "/static/js/templates_picker.js?v=1",
  "/static/js/todos.js?v=1",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches
      .open(VERSION)
      .then(function (cache) {
        return cache.addAll(PRECACHE);
      })
      .catch(function () {
        /* 单个资源失败不影响安装 */
      })
      .then(function () {
        return self.skipWaiting();
      })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (keys) {
        return Promise.all(
          keys.filter(function (key) {
            return key !== VERSION;
          }).map(function (key) {
            return caches.delete(key);
          })
        );
      })
      .then(function () {
        return self.clients.claim();
      })
  );
});

function isStatic(url) {
  return url.pathname.startsWith("/static/") || url.pathname.startsWith("/media/");
}

self.addEventListener("fetch", function (event) {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // 接口与流式响应不缓存
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ai/")) return;

  if (isStatic(url)) {
    event.respondWith(
      caches.match(request).then(function (cached) {
        if (cached) return cached;
        return fetch(request).then(function (response) {
          const copy = response.clone();
          caches.open(VERSION).then(function (cache) {
            cache.put(request, copy);
          });
          return response;
        });
      })
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then(function (response) {
          // 在线时把页面顺手缓存一份，断网后仍可回看
          const copy = response.clone();
          caches.open(VERSION).then(function (cache) {
            cache.put(request, copy);
          });
          return response;
        })
        .catch(function () {
          return caches.match(request).then(function (cached) {
            return cached || caches.match("/offline/");
          });
        })
    );
  }
});
