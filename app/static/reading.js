"use strict";
/* Format AQI reading source, local observation timestamp, relative age, and PM values. */
(function (root) {
  const I18n = root.CleanAirI18n || (typeof require !== "undefined" ? require("./i18n.js") : null);
  // Open-Meteo updates hourly; warn once observations are older than 3 hours.
  const STALE_MS = 3 * 60 * 60 * 1000;

  /**
   * Translate a reading label using CleanAirI18n or fallback strings.
   * @param {string|undefined} lang Active language code.
   * @param {string} key Message key.
   * @param {Record<string, string|number>} [params] Placeholder values.
   * @returns {string} Localized label.
   */
  function msg(lang, key, params) {
    return I18n ? I18n.tr(lang, key, params) : "";
  }

  /**
   * Format an elapsed duration in milliseconds as relative minutes or hours.
   * @param {number} diffMs Elapsed milliseconds since reading time.
   * @param {string} [lang] Language code for relative units.
   * @returns {string} Relative time phrase.
   */
  function formatRelative(diffMs, lang = "en") {
    const mins = Math.max(0, Math.floor(diffMs / 60000));
    if (mins < 60) return msg(lang, "reading_min_ago", {n: mins});
    const hours = Math.floor(mins / 60);
    return msg(lang, "reading_h_ago", {n: hours});
  }

  /**
   * Format a Date in the caller's locale using medium date and short time.
   * @param {Date} dt Parsed observation Date object.
   * @param {string|undefined} locale Optional BCP 47 locale tag.
   * @returns {string} Localized date-time string.
   */
  function formatLocalTime(dt, locale) {
    return new Intl.DateTimeFormat(locale, {dateStyle: "medium", timeStyle: "short"}).format(dt);
  }

  /**
   * Format available PM2.5 and PM10 particulate concentrations.
   * @param {number|null|undefined} pm25 Finite PM2.5 value in ug/m3.
   * @param {number|null|undefined} pm10 Finite PM10 value in ug/m3.
   * @returns {string} Dot-separated particulate string or empty string.
   */
  function formatPm(pm25, pm10) {
    const parts = [];
    if (typeof pm25 === "number" && Number.isFinite(pm25)) parts.push(`PM2.5 ${pm25.toFixed(1)} \u00b5g/m\u00b3`);
    if (typeof pm10 === "number" && Number.isFinite(pm10)) parts.push(`PM10 ${pm10.toFixed(1)} \u00b5g/m\u00b3`);
    return parts.join(" \u00b7 ");
  }

  /**
   * Format the localized reading timestamp, relative age, and stale warning suffix.
   * @param {string|null|undefined} rawTime ISO 8601 observation timestamp.
   * @param {number} nowMs Reference current timestamp in milliseconds.
   * @param {string|undefined} locale Optional BCP 47 locale tag.
   * @param {string} [lang] Language code for reading labels.
   * @returns {string} Formatted reading-time clause or empty string.
   */
  function formatTimeClause(rawTime, nowMs, locale, lang = "en") {
    if (!rawTime) return "";
    const dt = new Date(rawTime);
    if (Number.isNaN(dt.getTime())) return "";
    const diffMs = nowMs - dt.getTime();
    const stale = diffMs > STALE_MS ? msg(lang, "reading_stale") : "";
    return `${msg(lang, "reading_time", {time: formatLocalTime(dt, locale), rel: formatRelative(diffMs, lang)})}${stale}`;
  }

  /**
   * Resolve the explicit locale or default BCP 47 tag for a language.
   * @param {string} lang Normalized language code.
   * @param {string|undefined} locale Explicit override locale.
   * @returns {string|undefined} Resolved locale tag.
   */
  function localeTag(lang, locale) {
    if (locale !== undefined) return locale;
    return I18n ? I18n.localeFor(lang) : undefined;
  }

  /**
   * Format the single reading-metadata line shown below the AQI gauge.
   * @param {object|null|undefined} data Plan response payload with source, timestamp, and PM values.
   * @param {number} [nowMs] Reference timestamp in milliseconds.
   * @param {string|undefined} [locale] Optional BCP 47 locale tag.
   * @returns {string} Full reading attribution and freshness summary line.
   */
  function formatReadingMeta(data, nowMs = Date.now(), locale = undefined) {
    const d = data || {};
    const lang = I18n ? I18n.normalizeLang(d.lang) : "en";
    const src = d.source ? String(d.source) : "Open-Meteo";
    const clause = formatTimeClause(d.observed_at, nowMs, localeTag(lang, locale), lang);
    const pm = formatPm(d.pm2_5, d.pm10);
    return msg(lang, "reading_source", {source: src}) + clause + (pm ? ` \u00b7 ${pm}` : "");
  }

  const api = {formatReadingMeta, formatRelative, formatPm, STALE_MS};
  root.CleanAirReading = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
