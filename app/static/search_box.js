"use strict";
/* City and 6-digit PIN code autocomplete combobox with keyboard navigation. */
(function (root) {
  const Dom = root.CleanAirDom || (typeof require !== "undefined" ? require("./dom.js") : null);
  const MIN_QUERY_LEN = 2;

  let opts = [], active = -1, timer = null, seq = 0, ui = {};

  /**
   * Compute wrapped option index when moving up or down in the autocomplete listbox.
   * @param {number} current Active option index or -1.
   * @param {number} length Total number of listbox options.
   * @param {number} delta Step direction (+1 or -1).
   * @returns {number} Next valid option index or -1 when empty.
   */
  function nextActiveIndex(current, length, delta) {
    if (!length) return -1;
    return (current + delta + length) % length;
  }

  /**
   * Hide and clear the autocomplete suggestion listbox and ARIA selection state.
   * @returns {void}
   */
  function closeList() {
    ui.list.hidden = true;
    ui.list.replaceChildren();
    opts = [];
    active = -1;
    ui.cityIn.setAttribute("aria-expanded", "false");
    ui.cityIn.removeAttribute("aria-activedescendant");
  }

  /**
   * Pick a suggestion item by index, close the listbox, and invoke onPick.
   * @param {number} index Selected option index.
   * @returns {void}
   */
  function choose(index) {
    const picked = opts[index];
    if (!picked) return;
    closeList();
    ui.onPick(picked);
  }

  /**
   * Update highlighted option ARIA attributes during keyboard navigation.
   * @param {number} index Option index to activate (-1 clears active state).
   * @returns {void}
   */
  function setActive(index) {
    [...ui.list.children].forEach((li, j) => li.setAttribute("aria-selected", String(j === index)));
    active = index;
    if (index >= 0) ui.cityIn.setAttribute("aria-activedescendant", "opt-" + index);
    else ui.cityIn.removeAttribute("aria-activedescendant");
  }

  /**
   * Populate and show autocomplete listbox options from API results.
   * @param {Array<{label: string, lat: number, lon: number}>} items Suggestion items.
   * @returns {void}
   */
  function showList(items) {
    closeList();
    opts = items;
    items.forEach((item, i) => {
      const li = Dom.el("li", item.label);
      li.id = "opt-" + i;
      li.setAttribute("role", "option");
      // Select on mousedown before input blur closes the listbox.
      li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(i); });
      ui.list.append(li);
    });
    ui.list.hidden = !items.length;
    ui.cityIn.setAttribute("aria-expanded", String(items.length > 0));
  }

  /**
   * Execute an explicit Enter-key search (enables Nominatim PIN fallback) and pick top match.
   * @param {string} query Trimmed user city or 6-digit PIN query.
   * @returns {Promise<void>} Resolves when search results or fallback status render.
   */
  async function searchExplicit(query) {
    const mine = ++seq;
    try {
      const resp = await fetch("/api/places?q=" + encodeURIComponent(query) + "&explicit=1");
      const data = await resp.json();
      if (mine !== seq) return;
      const results = data.results || [];
      if (results.length > 0) {
        showList(results);
        choose(0);
      } else {
        closeList();
        ui.geoSt.textContent = "No match found. Check the spelling, try the 6-digit pincode, or click the map.";
      }
    } catch (_) {
      closeList();
      ui.geoSt.textContent = "Search unavailable. Click the map to choose your location.";
    }
  }

  /**
   * Debounce typeahead input events and fetch non-explicit place suggestions.
   * @returns {void}
   */
  function onInput() {
    ui.onClear();
    clearTimeout(timer);
    const q = ui.cityIn.value.trim();
    if (q.length < MIN_QUERY_LEN) { closeList(); return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const resp = await fetch("/api/places?q=" + encodeURIComponent(q));
        const data = await resp.json();
        if (mine === seq) showList(data.results || []);
      } catch (_) { closeList(); }
    }, Dom.CONFIG.DEBOUNCE_MS);
  }

  /**
   * Handle Enter, ArrowUp, ArrowDown, and Escape keys on the city combobox.
   * @param {KeyboardEvent} e Keydown event on the city input.
   * @returns {Promise<void>} Resolves once key handling finishes.
   */
  async function onKeyDown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (!ui.list.hidden && opts.length > 0) { choose(active >= 0 ? active : 0); return; }
      clearTimeout(timer);
      const q = ui.cityIn.value.trim();
      if (q.length >= MIN_QUERY_LEN) await searchExplicit(q);
      return;
    }
    if (ui.list.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(nextActiveIndex(active, opts.length, 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(nextActiveIndex(active, opts.length, -1)); }
    else if (e.key === "Escape") closeList();
  }

  /**
   * Bind input, keyboard, and blur event handlers for autocomplete search.
   * @param {object} refs DOM references and selection callbacks.
   * @returns {void}
   */
  function init(refs) {
    ui = refs;
    ui.cityIn.addEventListener("input", onInput);
    ui.cityIn.addEventListener("keydown", onKeyDown);
    ui.cityIn.addEventListener("blur", () => setTimeout(closeList, Dom.CONFIG.BLUR_CLOSE_MS));
  }

  const api = {init, nextActiveIndex};
  root.CleanAirSearch = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
