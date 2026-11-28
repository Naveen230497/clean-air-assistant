"use strict";
// Run with: node --test tests/reading.test.js
const test = require("node:test");
const assert = require("node:assert");
const R = require("../app/static/reading.js");

const NOW = Date.parse("2026-11-25T18:00:00Z");

test("shows only source when observed_at is null or invalid", () => {
  assert.strictEqual(R.formatReadingMeta({source: "Entered by you", observed_at: null}, NOW, "en-US"), "Source: Entered by you");
  assert.strictEqual(
    R.formatReadingMeta({source: "Read from your screenshot", observed_at: "bad-date"}, NOW, "en-US"),
    "Source: Read from your screenshot"
  );
});

test("formats relative minutes and hours without warning within 3 hours", () => {
  const minAgo = new Date(NOW - 15 * 60000).toISOString();
  const sMin = R.formatReadingMeta({source: "Open-Meteo", observed_at: minAgo}, NOW, "en-US");
  assert.match(sMin, /^Source: Open-Meteo\. Reading time: .+\(15 min ago\)$/);
  assert.doesNotMatch(sMin, /out of date/);

  const exact3h = new Date(NOW - 3 * 3600 * 1000).toISOString();
  const s3h = R.formatReadingMeta({source: "Open-Meteo", observed_at: exact3h}, NOW, "en-US");
  assert.match(s3h, /\(3 h ago\)$/);
  assert.doesNotMatch(s3h, /out of date/);
});

test("adds stale warning when observed_at is older than 3 hours", () => {
  const oldIso = new Date(NOW - (3 * 3600 + 60) * 1000).toISOString();
  const text = R.formatReadingMeta({source: "Open-Meteo", observed_at: oldIso}, NOW, "en-US");
  assert.match(text, /\(3 h ago\)\. This reading may be out of date\.$/);
});

test("includes PM2.5 and PM10 only when present", () => {
  const iso = new Date(NOW - 10 * 60000).toISOString();
  const withPm = R.formatReadingMeta(
    {source: "Open-Meteo", observed_at: iso, pm2_5: 12.3, pm10: 40.1},
    NOW,
    "en-US"
  );
  assert.match(withPm, /PM2\.5 12\.3 µg\/m³ · PM10 40\.1 µg\/m³/);

  const noPm = R.formatReadingMeta(
    {source: "Open-Meteo", observed_at: iso, pm2_5: null, pm10: null},
    NOW,
    "en-US"
  );
  assert.doesNotMatch(noPm, /PM2\.5|PM10/);
});
