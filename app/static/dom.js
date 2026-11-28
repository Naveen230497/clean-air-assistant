"use strict";
/* Shared DOM helpers, constants, validation regexes, and fetch wrapper. */
(function (root) {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const CONFIG = {
    MAX_AQI: 500,
    GAUGE_RADIUS: 80,
    MAX_IMAGE_BYTES: 3 * 1024 * 1024,
    MAX_HISTORY: 6,
    COORD_ACCURACY_CAP_M: 5000,
    DEBOUNCE_MS: 250,
    BLUR_CLOSE_MS: 150,
    STORAGE_KEY: "cleanair.lastLocation",
    NAME_RE: /^[\p{L}\p{N}_ .,'\-]{2,60}$/u,
    ALLOWED_IMAGE_RE: /^image\/(png|jpeg|webp)$/,
  };

  /**
   * Look up a DOM element by its ID.
   * @param {string} id Element ID attribute.
   * @returns {HTMLElement|null} Matching DOM element or null.
   */
  function byId(id) {
    return document.getElementById(id);
  }

  /**
   * Create an HTML element with optional textContent and CSS class.
   * @param {string} tag HTML tag name.
   * @param {string|number|undefined} [text] Safe text content assigned via textContent.
   * @param {string} [cls] Optional CSS class name.
   * @returns {HTMLElement} Created element node.
   */
  function el(tag, text, cls) {
    const node = document.createElement(tag);
    // Use textContent only so untrusted strings can never inject HTML.
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  /**
   * Create an SVG element in the SVG namespace with attributes.
   * @param {string} tag SVG tag name.
   * @param {Record<string, string|number>} attrs Attribute key-value pairs.
   * @returns {SVGElement} Created SVG node.
   */
  function svgEl(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    return node;
  }

  /**
   * Send a JSON POST request and parse its JSON response.
   * @param {string} url Request endpoint path.
   * @param {object} body Request JSON body.
   * @returns {Promise<object>} Parsed response payload.
   */
  async function postJson(url, body) {
    const resp = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const err = new Error(data.error || "Something went wrong");
      err.data = data;
      throw err;
    }
    return data;
  }

  /**
   * Return true if the label is a generic coordinate fallback string.
   * @param {string} text Place display label.
   * @returns {boolean} True when text begins with "Lat ".
   */
  function isCoordLabel(text) {
    return /^Lat\s+-?\d/i.test((text || "").trim());
  }

  /**
   * Extract a city prefix from a full place label when non-generic.
   * @param {string} place Place display string.
   * @returns {string} Extracted city name or empty string.
   */
  function cityFromPlace(place) {
    if (!place || isCoordLabel(place)) return "";
    const low = place.toLowerCase();
    if (low === "your location" || low === "selected location") return "";
    return place.split(",")[0].trim();
  }

  /**
   * Validate a place label against the client whitelist regex.
   * @param {string} name Candidate place name.
   * @returns {boolean} True when valid.
   */
  function validPlaceName(name) {
    return CONFIG.NAME_RE.test(name || "");
  }

  /**
   * Build a safe external anchor opening in a new tab.
   * @param {string} label Link text.
   * @param {string} url Destination URL.
   * @returns {HTMLAnchorElement} Configured anchor element.
   */
  function externalLink(label, url) {
    const a = el("a", label);
    a.href = url;
    a.rel = "noopener noreferrer";
    a.target = "_blank";
    return a;
  }

  /**
   * Build a paragraph wrapping an external link.
   * @param {string} label Link text.
   * @param {string} url Destination URL.
   * @returns {HTMLParagraphElement} Paragraph node with link.
   */
  function createLinkParagraph(label, url) {
    const p = el("p", undefined, "src");
    p.append(externalLink(label, url));
    return p;
  }

  const api = {CONFIG, byId, el, svgEl, postJson, isCoordLabel, cityFromPlace, validPlaceName, externalLink, createLinkParagraph};
  root.CleanAirDom = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
