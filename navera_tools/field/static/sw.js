// NAVERA Sky Test - the installed app opens even when the Jetson cannot be reached: the page shell is
// kept on the phone (network first, the copy when offline). Live data (/api/*) is never cached: the page
// shows "Waiting for NAVERA..." and keeps the phone's readings until the link is back.
"use strict";
var CACHE = "navera-sky-v1";
var SHELL = ["/field", "/manifest.webmanifest", "/static/icon-192.png", "/static/icon-512.png"];

self.addEventListener("install", function (ev) {
  ev.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) {
      return fetch(u, {credentials: "same-origin"}).then(function (r) { if (r.ok) return c.put(u, r); }).catch(function () {});
    }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (ev) {
  ev.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (ev) {
  var req = ev.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.indexOf("/api/") === 0) return;
  var page = req.mode === "navigate" && (url.pathname === "/" || url.pathname === "/field");
  if (!page && SHELL.indexOf(url.pathname) < 0) return;
  ev.respondWith(fetch(req).then(function (r) {
    if (r.ok && r.type === "basic") {
      var copy = r.clone();
      caches.open(CACHE).then(function (c) { c.put(page ? "/field" : url.pathname, copy); });
    }
    return r;
  }).catch(function () {
    return caches.match(page ? "/field" : url.pathname).then(function (hit) {
      return hit || new Response("<!doctype html><meta name=viewport content='width=device-width'><body style='font:18px system-ui;" +
        "padding:24px;background:#0b0d12;color:#d9dde8'><h2>Waiting for NAVERA...</h2><p>The phone cannot reach the Jetson. " +
        "Check it is on and on the same Wi-Fi or hotspot, then reopen the app.</p>",
        {headers: {"Content-Type": "text/html; charset=utf-8"}});
    });
  }));
});
