"use strict";
/* Location engine: listens to the device for a few seconds and keeps the MOST ACCURATE fix.
 * Works the same on phones (GPS) and laptops (Wi-Fi/network); the reported accuracy tells the
 * truth about how exact the fix is. No dependencies, no network calls: browser API only. */
(function (root) {
  const I18n = root.CleanAirI18n || (typeof require !== "undefined" ? require("./i18n.js") : null);
  const LIMITS = {precise: 150, good: 1500, approximate: 5000};

  /**
   * Look up a localized geolocation message with English fallback.
   * @param {string|undefined} lang Explicit language code or undefined for active page language.
   * @param {string} key Translation message key.
   * @param {Record<string, string|number>} [params] Placeholder substitutions.
   * @returns {string} Localized text.
   */
  function tr(lang, key, params) {
    const code = I18n ? I18n.normalizeLang(lang || I18n.getPageLang()) : "en";
    return I18n ? I18n.tr(code, key, params) : "";
  }

  /**
   * Map a geolocation accuracy radius in metres to a coarse/precise tier.
   * @param {number} m Horizontal accuracy in metres.
   * @returns {"precise"|"good"|"approximate"|"coarse"} Quality tier label.
   */
  const quality = (m) => (m <= LIMITS.precise ? "precise" : m <= LIMITS.good ? "good"
    : m <= LIMITS.approximate ? "approximate" : "coarse");

  /**
   * Format an accuracy distance in metres or kilometres.
   * @param {number} m Distance in metres.
   * @param {string} [lang] Optional language code override.
   * @returns {string} Rounded display distance.
   */
  const fmt = (m, lang) => {
    const isKm = m >= 1000;
    const val = isKm ? (m / 1000).toFixed(m >= 10000 ? 0 : 1) : Math.round(m);
    const unit = tr(lang, isKm ? "unit_km" : "unit_m") || (isKm ? "km" : "m");
    return `${val} ${unit}`;
  };

  /**
   * Build a geolocation Error carrying a standard status code.
   * @param {number} code Error status code (0-3).
   * @param {string|null} [message] Optional explicit error message.
   * @param {string} [lang] Optional language code.
   * @returns {Error & {code: number}} Error instance with numeric code.
   */
  function fail(code, message, lang) {
    const text = message || tr(lang, "loc_err_" + code) || tr(lang, "loc_err_generic") || "Could not get your location.";
    const e = new Error(text);
    e.code = code;
    return e;
  }

  /**
   * Normalize a GeolocationPosition into a CleanAirLocate fix object.
   * @param {GeolocationPosition} p Raw browser geolocation reading.
   * @returns {{lat: number, lon: number, accuracy: number, quality: string, timestamp: number}} Normalized fix.
   */
  function toFix(p) {
    return {lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy,
            quality: quality(p.coords.accuracy), timestamp: p.timestamp};
  }

  /**
   * Validate finite coordinate bounds and accuracy on a GeolocationPosition.
   * @param {GeolocationPosition|null|undefined} p Raw browser position object.
   * @returns {boolean} True when latitude, longitude, and accuracy are valid numbers.
   */
  const sane = (p) => p && p.coords && Number.isFinite(p.coords.latitude) && Number.isFinite(p.coords.longitude)
    && Math.abs(p.coords.latitude) <= 90 && Math.abs(p.coords.longitude) <= 180
    && Number.isFinite(p.coords.accuracy);

  /**
   * Resolve with the best fix seen; stops early once accuracy <= opts.good metres.
   * @param {{good?: number, maxWait?: number, onProgress?: (acc: number) => void, lang?: string}} [opts] Settling options.
   * @param {Geolocation|null} [geo] Geolocation API provider (defaults to navigator.geolocation).
   * @returns {Promise<{lat: number, lon: number, accuracy: number, quality: string, timestamp: number}>} Best fix.
   */
  function detect(opts = {}, geo = root.navigator && root.navigator.geolocation) {
    const {good = 50, maxWait = 20000, onProgress, lang} = opts;
    return new Promise((resolve, reject) => {
      if (!geo) return reject(fail(0, null, lang));
      if (root.isSecureContext === false) return reject(fail(0, tr(lang, "loc_err_https"), lang));
      let best = null, done = false, watchId = null, timer = null;
      const finish = (err, value) => {
        if (done) return;
        done = true;
        if (watchId !== null) geo.clearWatch(watchId);
        clearTimeout(timer);
        if (err) reject(err); else resolve(value);
      };
      watchId = geo.watchPosition(
        (p) => {
          if (!sane(p)) return;
          if (!best || p.coords.accuracy < best.coords.accuracy) best = p;
          if (onProgress) onProgress(best.coords.accuracy);
          if (best.coords.accuracy <= good) finish(null, toFix(best));
        },
        (e) => (best ? finish(null, toFix(best)) : finish(fail(e && e.code, null, lang))),
        {enableHighAccuracy: true, timeout: maxWait, maximumAge: 0});
      timer = setTimeout(() => (best ? finish(null, toFix(best)) : finish(fail(3, null, lang))), maxWait);
    });
  }

  /**
   * Build an honest user-facing description of a geolocation fix's accuracy.
   * @param {{accuracy: number, quality: string}} fix Normalized geolocation fix.
   * @param {string} [lang] Optional language code override.
   * @returns {string} User-facing status description.
   */
  function describe(fix, lang) {
    const keys = {
      precise: "loc_desc_precise", good: "loc_desc_good",
      approximate: "loc_desc_approx", coarse: "loc_desc_coarse",
    };
    const key = keys[fix.quality] || "loc_desc_coarse";
    return tr(lang, key, {a: fmt(fix.accuracy, lang)});
  }

  const MAX_AGE_MS = 24 * 60 * 60 * 1000;

  /**
   * Return true if the saved record is missing, corrupted, lacks a timestamp, or is older than maxAgeMs.
   * @param {{ts?: number}|null|undefined} saved Stored location record.
   * @param {number} [now] Current epoch timestamp in milliseconds.
   * @param {number} [maxAgeMs] Maximum valid age in milliseconds.
   * @returns {boolean} True when expired or invalid.
   */
  function isSavedExpired(saved, now = Date.now(), maxAgeMs = MAX_AGE_MS) {
    if (!saved || typeof saved !== "object") return true;
    if (typeof saved.ts !== "number" || !Number.isFinite(saved.ts)) return true;
    const age = now - saved.ts;
    return age < 0 || age > maxAgeMs;
  }

  const api = {detect, describe, quality, fmt, LIMITS, isSavedExpired, MAX_AGE_MS};
  root.CleanAirLocate = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
