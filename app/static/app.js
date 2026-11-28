"use strict";
/* Top-level application coordinator binding form submission and UI modules. */
(function () {
  const Dom = window.CleanAirDom;
  const PlanView = window.CleanAirPlanView;
  const MapLoc = window.CleanAirMap;
  const Search = window.CleanAirSearch;
  const Extras = window.CleanAirExtras;

  const form = Dom.byId("form");
  const out = Dom.byId("results");
  const btn = Dom.byId("go");
  const aqiIn = Dom.byId("aqi");
  const cityIn = Dom.byId("city");
  const geoSt = Dom.byId("geo-status");
  const forgetBtn = Dom.byId("forget");

  let aqiFromImage = false;

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
    const disp = data.place && data.place !== "Your location" ? data.place : (coords.place || "Selected location");
    const hint = coords.isManualOrApprox ? " Drag the pin to adjust your exact spot." : "";
    geoSt.textContent = `\uD83D\uDCCD Selected: ${disp}.${hint}`;
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
    const placeName = data.place && data.place !== "Your location"
      ? data.place
      : (coords?.place || data.place || "Selected location");
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
    out.setAttribute("aria-busy", "true");
    btn.disabled = true;
    out.replaceChildren(PlanView.createSkeleton());
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
    cityIn, drop: Dom.byId("drop"), photoInput: Dom.byId("photo"), cameraInput: Dom.byId("camera"),
    photoStatus: Dom.byId("photo-status"), advBtn: Dom.byId("adv-btn"), advOut: Dom.byId("adv-out"),
    chatForm: Dom.byId("chat-form"), qInput: Dom.byId("q"), qBtn: Dom.byId("q-btn"),
    chatLog: Dom.byId("chat-log"), nearBtn: Dom.byId("near-btn"), nearOut: Dom.byId("near-out"),
    extrasSection: Dom.byId("extras"),
    onImageAqi: (aqi) => { aqiIn.value = aqi; aqiFromImage = true; },
  });

  aqiIn.addEventListener("input", () => { aqiFromImage = false; });
  form.addEventListener("submit", onSubmitPlan);
})();
