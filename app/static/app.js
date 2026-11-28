"use strict";
/* Top-level application coordinator binding form submission and UI modules. */
(function () {
  const Dom = window.CleanAirDom;
  const PlanView = window.CleanAirPlanView;
  const MapLoc = window.CleanAirMap;
  const Search = window.CleanAirSearch;
  const Extras = window.CleanAirExtras;
  const I18n = window.CleanAirI18n;

  const form = Dom.byId("form");
  const out = Dom.byId("results");
  const btn = Dom.byId("go");
  const aqiIn = Dom.byId("aqi");
  const cityIn = Dom.byId("city");
  const geoSt = Dom.byId("geo-status");
  const forgetBtn = Dom.byId("forget");

  let aqiFromImage = false;

  /**
   * Look up a localized UI label using CleanAirI18n.
   * @param {string} lang Language code.
   * @param {string} key Translation message key.
   * @param {Record<string, string|number>} [params] Optional placeholder values.
   * @returns {string} Localized label text.
   */
  function tr(lang, key, params) {
    return I18n ? I18n.tr(lang, key, params) : "";
  }

  /**
   * Read the active UI language code safely.
   * @returns {string} Active normalized language code.
   */
  function currentLang() {
    const raw = form.elements.lang?.value || Dom.byId("lang")?.value || (I18n && I18n.getPageLang());
    return I18n ? I18n.normalizeLang(raw) : "en";
  }

  /**
   * Resolve a readable display place label for the active plan and language.
   * @param {object} data Plan API response payload.
   * @param {{place?: string}|null} coords Active coordinates.
   * @param {string} lang Active language code.
   * @returns {string} Resolved display place name.
   */
  function resolveDisplayPlace(data, coords, lang) {
    if (data.place && data.place !== "Your location") return data.place;
    return coords?.place || data.place || tr(lang, "selected_default") || "Selected location";
  }

  /**
   * Synchronize status text, saved storage, and city input after plan resolution.
   * @param {object} data Plan API response payload.
   * @param {{lat: number, lon: number, place?: string, isManualOrApprox?: boolean}|null} coords Active coordinates.
   * @returns {void}
   */
  function syncDetectedPlace(data, coords) {
    if (Boolean(aqiIn.value.trim())) return;
    MapLoc.saveLocation(data);
    if (!coords) return;
    const lang = I18n ? I18n.normalizeLang(data.lang || currentLang()) : "en";
    const disp = resolveDisplayPlace(data, coords, lang);
    const hint = coords.isManualOrApprox ? tr(lang, "drag_pin_hint") : "";
    geoSt.textContent = tr(lang, "selected_place", {place: disp, hint});
    const c = Dom.cityFromPlace(disp);
    if (c) cityIn.value = c;
  }

  /**
   * Render the built plan, sync place UI, and unlock secondary panels.
   * @param {object} data Plan API response payload.
   * @param {{lat: number, lon: number, place?: string, isManualOrApprox?: boolean}|null} coords Active coordinates.
   * @returns {void}
   */
  function handlePlanSuccess(data, coords) {
    const lang = I18n ? I18n.normalizeLang(data.lang || currentLang()) : "en";
    const placeName = resolveDisplayPlace(data, coords, lang);
    PlanView.renderPlan(out, data, placeName);
    syncDetectedPlace(data, coords);
    Extras.resetContext(
      {aqi: data.aqi, place: Dom.validPlaceName(placeName) ? placeName : "your area", lang: data.lang},
      coords ? {lat: coords.lat, lon: coords.lon} : null
    );
  }

  /**
   * Handle plan form submission and render loading, result, or error UI.
   * @param {Event} e Form submit event.
   * @returns {Promise<void>} Resolves when submission cycle completes.
   */
  async function onSubmitPlan(e) {
    e.preventDefault();
    const lang = currentLang();
    out.setAttribute("aria-busy", "true");
    out.setAttribute("lang", lang);
    btn.disabled = true;
    out.replaceChildren(PlanView.createSkeleton(lang));
    try {
      const coords = MapLoc.getCoords();
      const body = PlanView.buildPayload(form, coords, aqiFromImage);
      handlePlanSuccess(await Dom.postJson("/api/plan", body), coords);
    } catch (err) {
      out.replaceChildren(Dom.el("p", err.message, "card err"));
    } finally {
      out.setAttribute("aria-busy", "false");
      btn.disabled = false;
      out.focus();
    }
  }

  if (I18n) {
    I18n.initPageI18n(document, (nextLang) => {
      out.setAttribute("lang", nextLang);
    });
  }

  MapLoc.init({
    form, cityIn, geoSt, forgetBtn,
    geoBtn: Dom.byId("geo"),
    mapCoordsEl: Dom.byId("map-coords"),
    onLocationPicked: (city) => {
      aqiIn.value = "";
      aqiFromImage = false;
      if (city) cityIn.value = city;
    },
  });

  Search.init({
    cityIn, geoSt,
    list: Dom.byId("city-list"),
    onClear: () => { MapLoc.clearCoords(); geoSt.textContent = ""; forgetBtn.hidden = true; },
    onPick: (picked) => { MapLoc.clearAccCircle(); MapLoc.setExactLocation(picked.lat, picked.lon, picked.label, true, true); },
  });

  Extras.init({
    cityIn, langSelect: Dom.byId("lang"), drop: Dom.byId("drop"), photoInput: Dom.byId("photo"), cameraInput: Dom.byId("camera"),
    photoStatus: Dom.byId("photo-status"), advBtn: Dom.byId("adv-btn"), advOut: Dom.byId("adv-out"),
    chatForm: Dom.byId("chat-form"), qInput: Dom.byId("q"), qBtn: Dom.byId("q-btn"),
    chatLog: Dom.byId("chat-log"), nearBtn: Dom.byId("near-btn"), nearOut: Dom.byId("near-out"),
    extrasSection: Dom.byId("extras"),
    onImageAqi: (aqi) => { aqiIn.value = aqi; aqiFromImage = true; },
  });

  aqiIn.addEventListener("input", () => { aqiFromImage = false; });
  form.addEventListener("submit", onSubmitPlan);
})();
