"use strict";
/* Plan payload assembly, SVG AQI gauge, skeleton state, and action-card rendering. */
(function (root) {
  const Dom = root.CleanAirDom || (typeof require !== "undefined" ? require("./dom.js") : null);
  const LABELS = {
    routine: "\uD83D\uDD52 Daily routine",
    indoor: "\uD83C\uDFE0 Indoor air",
    alternative: "\uD83C\uDF31 Sustainable alternative",
  };
  const BOOL_FLAGS = ["children", "elderly", "respiratory", "has_purifier", "outdoor_exercise"];
  const ARC = Math.PI * Dom.CONFIG.GAUGE_RADIUS;
  const SKELETON_ROWS = 4;
  const SKELETON_START_PCT = 95;
  const SKELETON_STEP_PCT = 12;

  /**
   * Compute SVG arc dash lengths and rounded value for an AQI reading.
   * @param {number|string} aqi Numeric or string US AQI input.
   * @returns {{rounded: number, filled: number, total: number}} Arc geometry values.
   */
  function computeGaugeArc(aqi) {
    const ratio = Math.min(Math.max(Number(aqi) || 0, 0) / Dom.CONFIG.MAX_AQI, 1);
    return {rounded: Math.round(Number(aqi) || 0), filled: ratio * ARC, total: ARC};
  }

  /**
   * Build the /api/plan JSON request body honoring AQI > coordinates > city priority.
   * @param {object} fields Form field values.
   * @param {{lat: number, lon: number}|null} coords Active coordinates or null.
   * @param {boolean} aqiFromImage Whether AQI was extracted from an uploaded image.
   * @returns {object} Request payload ready for /api/plan.
   */
  function buildPayloadFromFields({commute, cooking, lang, city, aqi, flags}, coords, aqiFromImage) {
    const body = {commute, cooking, lang};
    const cleanCity = (city || "").trim();
    const cleanAqi = (aqi ?? "").toString().trim();
    if (cleanAqi) {
      body.aqi = Number(cleanAqi);
      if (aqiFromImage) body.aqi_source = "image";
    } else if (coords) {
      Object.assign(body, coords);
    } else if (cleanCity) {
      body.city = cleanCity;
    }
    Object.assign(body, flags || {});
    return body;
  }

  /**
   * Read form inputs and assemble the /api/plan payload.
   * @param {HTMLFormElement} form Main clean-air plan form.
   * @param {{lat: number, lon: number}|null} coords Active coordinates or null.
   * @param {boolean} aqiFromImage Whether AQI originated from image OCR/vision.
   * @returns {object} Request payload object.
   */
  function buildPayload(form, coords, aqiFromImage) {
    const f = new FormData(form);
    const flags = {};
    for (const k of BOOL_FLAGS) flags[k] = form.elements[k].checked;
    return buildPayloadFromFields({
      commute: f.get("commute"), cooking: f.get("cooking"), lang: f.get("lang"),
      city: f.get("city"), aqi: f.get("aqi"), flags,
    }, coords, aqiFromImage);
  }

  /**
   * Build the animated semicircular SVG gauge for an AQI reading.
   * @param {number} aqi Current US AQI value.
   * @param {number} level Severity band level (0-5).
   * @returns {SVGElement} SVG gauge element.
   */
  function createGauge(aqi, level) {
    const {rounded, filled, total} = computeGaugeArc(aqi);
    const svgNode = Dom.svgEl("svg", {
      viewBox: "0 0 200 125",
      class: "gauge lvl" + level,
      role: "img",
      "aria-label": `AQI ${aqi}`,
    });
    const arcPath = "M20 100 A80 80 0 0 1 180 100";
    const val = Dom.svgEl("path", {d: arcPath, class: "val", "stroke-dasharray": `0 ${total}`});
    const big = Dom.svgEl("text", {x: 100, y: 92, "font-size": 40, "font-weight": 800});
    big.textContent = rounded;
    const sm = Dom.svgEl("text", {x: 100, y: 116, "font-size": 12});
    sm.textContent = "US AQI";
    svgNode.append(Dom.svgEl("path", {d: arcPath, class: "track"}), val, big, sm);
    requestAnimationFrame(() => requestAnimationFrame(() => val.setAttribute("stroke-dasharray", `${filled} ${total}`)));
    return svgNode;
  }

  /**
   * Build the animated horizontal bar showing estimated exposure reduction.
   * @param {number} pct Exposure reduction percentage (0-85).
   * @returns {HTMLDivElement} Meter container element.
   */
  function createMeter(pct) {
    const meter = Dom.el("div", undefined, "meter");
    meter.setAttribute("role", "img");
    meter.setAttribute("aria-label", `Estimated exposure reduction ${pct} percent`);
    const bar = Dom.el("span");
    bar.style.width = "0%";
    meter.append(bar);
    requestAnimationFrame(() => requestAnimationFrame(() => { bar.style.width = pct + "%"; }));
    return meter;
  }

  /**
   * Render the top summary hero card containing gauge, briefing, and reduction meter.
   * @param {object} data Plan API response object.
   * @param {string} placeName Display location string.
   * @returns {HTMLDivElement} Rendered hero card element.
   */
  function createHeroCard(data, placeName) {
    const b = data.briefing;
    const hero = Dom.el("div", undefined, "card hero-card");
    const left = Dom.el("div");
    left.append(
      createGauge(data.aqi, data.level),
      Dom.el("span", `US AQI ${Math.round(Number(data.aqi) || 0)} (${data.band})`, "sr-only")
    );
    if (typeof root.CleanAirReading !== "undefined") {
      left.append(Dom.el("p", root.CleanAirReading.formatReadingMeta(data), "help reading-meta"));
    }
    const right = Dom.el("div");
    right.append(
      Dom.el("span", data.band, "pill lvl" + data.level),
      Dom.el("p", placeName, "place"),
      Dom.el("h2", b.headline, "headline"),
      Dom.el("p", b.summary)
    );
    if (b.top_three.length) {
      const ol = Dom.el("ol");
      b.top_three.forEach((t) => ol.append(Dom.el("li", t)));
      right.append(Dom.el("h3", "Top 3 today"), ol);
    }
    right.append(
      Dom.el("p", `Follow this plan: about ${data.est_reduction_pct}% less pollution exposure (rough estimate)`, "help"),
      createMeter(data.est_reduction_pct),
      Dom.el("span", `Estimated exposure reduction ${data.est_reduction_pct}%`, "sr-only")
    );
    if (b.myth_buster) right.append(Dom.el("p", "Myth buster: " + b.myth_buster, "myth"));
    const srcText = b.source === "gemini" ? "\u2728 Briefing written by Gemini" : "Briefing from built-in rules";
    right.append(Dom.el("p", srcText, "help"));
    hero.append(left, right);
    return hero;
  }

  /**
   * Render the categorized household action cards grid.
   * @param {Array<{category: string, title: string, why: string, impact: string}>} actions Plan actions list.
   * @returns {HTMLDivElement} Actions card container.
   */
  function createActionsCard(actions) {
    const card = Dom.el("div", undefined, "card");
    card.append(Dom.el("h2", "Your actions"));
    const grid = Dom.el("div", undefined, "grid");
    actions.forEach((a) => {
      const article = Dom.el("article", undefined, "act");
      article.append(
        Dom.el("span", LABELS[a.category] || a.category, "tag"),
        Dom.el("h3", a.title),
        Dom.el("p", a.why),
        Dom.el("p", "Impact: " + a.impact, "impact")
      );
      grid.append(article);
    });
    card.append(grid);
    return card;
  }

  /**
   * Create an animated loading skeleton card while /api/plan executes.
   * @returns {HTMLDivElement} Skeleton card element.
   */
  function createSkeleton() {
    const card = Dom.el("div", undefined, "card");
    card.append(Dom.el("p", "Building your plan\u2026", "help"));
    for (let i = 0; i < SKELETON_ROWS; i++) {
      const bar = Dom.el("div", undefined, "skel");
      bar.style.width = (SKELETON_START_PCT - i * SKELETON_STEP_PCT) + "%";
      card.append(bar);
    }
    return card;
  }

  /**
   * Replace results container children with the complete rendered air plan.
   * @param {HTMLElement} out Target results section element.
   * @param {object} data Plan API response object.
   * @param {string} placeName Resolved display place name.
   * @returns {void}
   */
  function renderPlan(out, data, placeName) {
    out.replaceChildren();
    out.append(createHeroCard(data, placeName));
    if (data.safety_note) out.append(Dom.el("p", data.safety_note, "card note"));
    out.append(createActionsCard(data.actions));
  }

  const api = {computeGaugeArc, buildPayloadFromFields, buildPayload, createSkeleton, renderPlan};
  root.CleanAirPlanView = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
