"use strict";
/* Format AQI reading source, local observation timestamp, relative age, and PM values. */
(function (root) {
  // Open-Meteo updates hourly; warn once observations are older than 3 hours.
  const STALE_MS = 3 * 60 * 60 * 1000;

  /**
   * Format an elapsed duration in milliseconds as relative minutes or hours.
   * @param {number} diffMs Elapsed milliseconds since reading time.
   * @returns {string} Relative time phrase.
   */
  function formatRelative(diffMs) {
    const mins = Math.max(0, Math.floor(diffMs / 60000));
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.floor(mins / 60);
    return `${hours} h ago`;
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
   * @returns {string} Formatted reading-time clause or empty string.
   */
  function formatTimeClause(rawTime, nowMs, locale) {
    if (!rawTime) return "";
    const dt = new Date(rawTime);
    if (Number.isNaN(dt.getTime())) return "";
    const diffMs = nowMs - dt.getTime();
    const stale = diffMs > STALE_MS ? ". This reading may be out of date." : "";
    return `. Reading time: ${formatLocalTime(dt, locale)} (${formatRelative(diffMs)})${stale}`;
  }

  /**
   * Format the single reading-metadata line shown below the AQI gauge.
   * @param {object|null|undefined} data Plan response payload with source, timestamp, and PM values.
   * @param {number} [nowMs] Reference timestamp in milliseconds.
   * @param {string|undefined} [locale] Optional BCP 47 locale tag.
   * @returns {string} Full reading attribution and freshness summary line.
   */
  function formatReadingMeta(data, nowMs = Date.now(), locale = undefined) {
    const src = (data && data.source) ? String(data.source) : "Open-Meteo";
    let line = `Source: ${src}${formatTimeClause(data && data.observed_at, nowMs, locale)}`;
    const pm = data ? formatPm(data.pm2_5, data.pm10) : "";
    if (pm) line += ` \u00b7 ${pm}`;
    return line;
  }

  const api = {formatReadingMeta, formatRelative, formatPm, STALE_MS};
  root.CleanAirReading = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
