"use strict";
/* Frontend UI message catalogs, safe English fallback, and whole-page DOM translator. */
(function (root) {
  const LANGS = ["en", "hi", "te", "ta", "bn", "mr"];
  const LOCALES = {en: undefined, hi: "hi-IN", te: "te-IN", ta: "ta-IN", bn: "bn-IN", mr: "mr-IN"};
  const LANG_STORAGE_KEY = "cleanair.lang";
  const PACKS = {};

  for (const code of LANGS) {
    const loaded = root.CleanAirLocales && root.CleanAirLocales[code];
    PACKS[code] = loaded || (typeof require !== "undefined" ? require(`./locales/${code}.js`) : {});
  }

  /**
   * Normalize an ISO language tag against the six supported languages.
   * @param {string|null|undefined} lang Candidate language code.
   * @returns {"en"|"hi"|"te"|"ta"|"bn"|"mr"} Supported language code defaulting to "en".
   */
  function normalizeLang(lang) {
    return Object.hasOwn(PACKS, lang) ? lang : "en";
  }

  /**
   * Return the BCP 47 locale tag associated with a supported language.
   * @param {string|null|undefined} lang Language code.
   * @returns {string|undefined} Locale tag or undefined for runtime default.
   */
  function localeFor(lang) {
    return LOCALES[normalizeLang(lang)];
  }

  /**
   * Format a localized frontend message with safe English fallback and parameter substitution.
   * @param {string|null|undefined} lang Language code.
   * @param {string} key Message identifier key.
   * @param {Record<string, string|number>} [params] Optional placeholder values.
   * @returns {string} Localized formatted text (or empty string if unknown key).
   */
  function tr(lang, key, params) {
    const code = normalizeLang(lang);
    const tmpl = PACKS[code][key] || PACKS.en[key] || "";
    if (!tmpl || !params) return tmpl;
    return tmpl.replace(/\{([a-zA-Z0-9_]+)\}/g, (m, k) => (Object.hasOwn(params, k) ? String(params[k]) : m));
  }

  /**
   * Read the user's saved language choice from localStorage safely.
   * @returns {"en"|"hi"|"te"|"ta"|"bn"|"mr"} Validated saved language or "en".
   */
  function getSavedLang() {
    try {
      const saved = root.localStorage && root.localStorage.getItem(LANG_STORAGE_KEY);
      return Object.hasOwn(PACKS, saved) ? saved : "en";
    } catch (_) {
      return "en";
    }
  }

  /**
   * Persist the user's selected language to localStorage safely.
   * @param {string|null|undefined} lang Candidate language code.
   * @returns {"en"|"hi"|"te"|"ta"|"bn"|"mr"} Normalized language code saved or active.
   */
  function saveLang(lang) {
    const code = normalizeLang(lang);
    try {
      if (root.localStorage) root.localStorage.setItem(LANG_STORAGE_KEY, code);
    } catch (_) {}
    return code;
  }

  /**
   * Return the active page language from selector or documentElement.
   * @param {Document} [doc] Document reference (defaults to global document).
   * @returns {"en"|"hi"|"te"|"ta"|"bn"|"mr"} Active normalized language code.
   */
  function getPageLang(doc = root.document) {
    if (!doc) return "en";
    const select = doc.getElementById && doc.getElementById("lang");
    return normalizeLang((select && select.value) || (doc.documentElement && doc.documentElement.lang));
  }

  /**
   * Apply translated textContent and attributes across declarative DOM elements.
   * @param {string|null|undefined} lang Target language code.
   * @param {Document} [doc] Target document (defaults to global document).
   * @returns {"en"|"hi"|"te"|"ta"|"bn"|"mr"} Normalized language code applied.
   */
  function applyPage(lang, doc = root.document) {
    const code = normalizeLang(lang);
    if (!doc) return code;
    if (doc.documentElement) doc.documentElement.lang = code;
    const title = tr(code, "page_title");
    if (title && typeof doc.title === "string") doc.title = title;
    const all = doc.querySelectorAll ? doc.querySelectorAll("[data-i18n],[data-i18n-lead],[data-i18n-attr]") : [];
    all.forEach((node) => applyElement(node, code));
    return code;
  }

  /**
   * Apply declarative translation attributes on a single DOM element.
   * @param {Element} node Target element with data-i18n* attributes.
   * @param {string} code Normalized target language code.
   * @returns {void}
   */
  function applyElement(node, code) {
    const key = node.getAttribute("data-i18n");
    if (key) node.textContent = tr(code, key);
    const leadKey = node.getAttribute("data-i18n-lead");
    if (leadKey && node.firstChild && node.firstChild.nodeType === 3) {
      node.firstChild.nodeValue = tr(code, leadKey);
    }
    const attrSpec = node.getAttribute("data-i18n-attr");
    if (!attrSpec) return;
    attrSpec.split(",").forEach((pair) => {
      const idx = pair.indexOf(":");
      if (idx > 0) node.setAttribute(pair.slice(0, idx).trim(), tr(code, pair.slice(idx + 1).trim()));
    });
  }

  /**
   * Initialize the top-level page language selector and live page translation binding.
   * @param {Document} [doc] Target document (defaults to global document).
   * @param {(lang: string) => void} [onChange] Optional callback invoked after switching languages.
   * @returns {"en"|"hi"|"te"|"ta"|"bn"|"mr"} Initialized active language code.
   */
  function initPageI18n(doc = root.document, onChange) {
    const select = doc && doc.getElementById ? doc.getElementById("lang") : null;
    const initial = getSavedLang();
    if (select) select.value = initial;
    applyPage(initial, doc);
    if (select && select.addEventListener) {
      select.addEventListener("change", () => {
        const next = applyPage(saveLang(select.value), doc);
        if (onChange) onChange(next);
      });
    }
    return initial;
  }

  const api = {
    LANGS, PACKS, normalizeLang, localeFor, tr,
    getSavedLang, saveLang, getPageLang, applyPage, initPageI18n,
  };
  root.CleanAirI18n = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
