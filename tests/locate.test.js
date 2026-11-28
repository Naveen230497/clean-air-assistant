"use strict";
// Run with: node --test tests/locate.test.js
const test = require("node:test");
const assert = require("node:assert");
const L = require("../app/static/locate.js");

const pos = (acc, lat = 16.3, lon = 80.45) => ({coords: {latitude: lat, longitude: lon, accuracy: acc}, timestamp: 1});

function fakeGeo(steps, errorAt = null) {
  const geo = {cleared: false};
  geo.watchPosition = (ok, err) => {
    steps.forEach((s, i) => setTimeout(() => (errorAt === i ? err({code: 2}) : ok(s)), 5 * (i + 1)));
    return 1;
  };
  geo.clearWatch = () => { geo.cleared = true; };
  return geo;
}

test("quality thresholds", () => {
  assert.strictEqual(L.quality(30), "precise");
  assert.strictEqual(L.quality(150), "precise");
  assert.strictEqual(L.quality(151), "good");
  assert.strictEqual(L.quality(1500), "good");
  assert.strictEqual(L.quality(4000), "approximate");
  assert.strictEqual(L.quality(5001), "coarse");
});

test("fmt formats metres and kilometres", () => {
  assert.strictEqual(L.fmt(42.4), "42 m");
  assert.strictEqual(L.fmt(1500), "1.5 km");
  assert.strictEqual(L.fmt(25000), "25 km");
});

test("keeps the most accurate fix, not the first or last", async () => {
  const geo = fakeGeo([pos(900), pos(30, 16.31), pos(400)]);
  const fix = await L.detect({good: 10, maxWait: 100}, geo);
  assert.strictEqual(fix.accuracy, 30);
  assert.strictEqual(fix.lat, 16.31);
  assert.strictEqual(fix.quality, "precise");
});

test("stops early once accuracy is good enough and clears the watch", async () => {
  const geo = fakeGeo([pos(800), pos(40), pos(5)]);
  const fix = await L.detect({good: 50, maxWait: 500}, geo);
  assert.strictEqual(fix.accuracy, 40);
  assert.ok(geo.cleared);
});

test("laptop-style coarse fix is reported honestly", async () => {
  const fix = await L.detect({good: 50, maxWait: 60}, fakeGeo([pos(25000)]));
  assert.strictEqual(fix.quality, "coarse");
  assert.match(L.describe(fix), /only place you within about 25 km/);
});

test("permission denied rejects with a friendly message", async () => {
  const geo = {watchPosition: (ok, err) => { setTimeout(() => err({code: 1}), 5); return 1; }, clearWatch() {}};
  await assert.rejects(L.detect({maxWait: 100}, geo), (e) => e.code === 1 && /blocked/.test(e.message));
});

test("error after a fix still returns the best fix", async () => {
  const fix = await L.detect({good: 1, maxWait: 200}, fakeGeo([pos(700), pos(900)], 1));
  assert.strictEqual(fix.accuracy, 700);
});

test("times out when nothing arrives", async () => {
  const geo = {watchPosition: () => 1, clearWatch() {}};
  await assert.rejects(L.detect({maxWait: 30}, geo), (e) => e.code === 3);
});

test("no geolocation support", async () => {
  await assert.rejects(L.detect({}, null), (e) => e.code === 0);
});

test("ignores invalid coordinates", async () => {
  const geo = fakeGeo([pos(10, 999, 0), pos(200)]);
  const fix = await L.detect({good: 1, maxWait: 100}, geo);
  assert.strictEqual(fix.accuracy, 200);
});

test("24-hour saved location expiry logic", () => {
  const now = 1700000000000;
  assert.strictEqual(L.isSavedExpired(null, now), true);
  assert.strictEqual(L.isSavedExpired({}, now), true);
  assert.strictEqual(L.isSavedExpired({lat: 17.4, lon: 78.4}, now), true, "legacy save without timestamp expires");
  assert.strictEqual(L.isSavedExpired({lat: 17.4, lon: 78.4, ts: "invalid"}, now), true);
  assert.strictEqual(L.isSavedExpired({lat: 17.4, lon: 78.4, ts: now - 3600 * 1000}, now), false, "1 hour old is valid");
  assert.strictEqual(L.isSavedExpired({lat: 17.4, lon: 78.4, ts: now - 23 * 3600 * 1000}, now), false, "23 hours old is valid");
  assert.strictEqual(L.isSavedExpired({lat: 17.4, lon: 78.4, ts: now - 25 * 3600 * 1000}, now), true, "25 hours old is expired");
  assert.strictEqual(L.isSavedExpired({lat: 17.4, lon: 78.4, ts: now + 100000}, now), true, "future timestamp is expired");
});
