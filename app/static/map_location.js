"use strict";
/* Interactive Leaflet map, pin dragging, browser geolocation, and saved location cache. */
(function (root) {
  const Dom = root.CleanAirDom || (typeof require !== "undefined" ? require("./dom.js") : null);
  const DEFAULT_VIEW = {lat: 20.5, lon: 79.0, zoom: 5};
  const PICK_ZOOM = 13;
  const FIT_MAX_GOOD = 17;
  const FIT_MAX_COARSE = 12;
  const COARSE_ZOOM = 10;
  const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const TILE_ATTR = "&copy; <a href=\"https://www.openstreetmap.org/copyright\" target=\"_blank\" rel=\"noopener noreferrer\">OpenStreetMap</a> contributors";

  let map = null, marker = null, accCircle = null, locSeq = 0, coords = null, ui = {};

  /**
   * Format a coordinates summary line with place label.
   * @param {number} lat Latitude coordinate.
   * @param {number} lon Longitude coordinate.
   * @param {string} place Display place name.
   * @returns {string} Formatted coordinate string.
   */
  function formatCoordsLine(lat, lon, place) {
    return `Lat: ${Number(lat).toFixed(4)}, Lon: ${Number(lon).toFixed(4)} \u2014 ${place}`;
  }

  /**
   * Check whether a saved localStorage location record is usable.
   * @param {object|null} v Parsed saved location object.
   * @returns {boolean} True when coordinates, accuracy, and name are valid.
   */
  function isValidSavedLocation(v) {
    if (!v || !Number.isFinite(v.lat) || !Number.isFinite(v.lon)) return false;
    if (v.accuracy && v.accuracy > Dom.CONFIG.COORD_ACCURACY_CAP_M) return false;
    return Dom.validPlaceName(v.place) && v.place.toLowerCase() !== "your location";
  }

  /**
   * Update the map coordinate caption element when present.
   * @param {number} lat Latitude coordinate.
   * @param {number} lon Longitude coordinate.
   * @param {string} label Display text next to coordinates.
   * @returns {void}
   */
  function showMapCoords(lat, lon, label) {
    if (ui.mapCoordsEl) ui.mapCoordsEl.textContent = formatCoordsLine(lat, lon, label);
  }

  /**
   * Build safe DOM content for the Leaflet marker popup.
   * @param {string} place Resolved location label.
   * @param {number} lat Latitude coordinate.
   * @param {number} lon Longitude coordinate.
   * @returns {HTMLDivElement} Popup DOM node.
   */
  function popupNode(place, lat, lon) {
    const box = Dom.el("div");
    box.append(Dom.el("strong", place), Dom.el("div", `Lat: ${lat.toFixed(4)}, Lon: ${lon.toFixed(4)}`, "popup-sub"));
    return box;
  }

  /**
   * Remove the Leaflet accuracy circle overlay if currently shown.
   * @returns {void}
   */
  function clearAccCircle() {
    if (accCircle && map) { map.removeLayer(accCircle); accCircle = null; }
  }

  /**
   * Place or move the draggable Leaflet pin and open its popup.
   * @param {number} lat Latitude coordinate.
   * @param {number} lon Longitude coordinate.
   * @param {string} place Display location label.
   * @returns {void}
   */
  function placeMarker(lat, lon, place) {
    if (!map || typeof L === "undefined") return;
    if (!marker) {
      const icon = L.icon({iconUrl: "/static/pin.svg", iconSize: [24, 36], iconAnchor: [12, 36], popupAnchor: [0, -34]});
      marker = L.marker([lat, lon], {draggable: true, icon}).addTo(map);
      marker.on("dragend", () => {
        const p = marker.getLatLng();
        clearAccCircle();
        setExactLocation(p.lat, p.lng, null, true, true);
      });
    } else {
      marker.setLatLng([lat, lon]);
    }
    marker.bindPopup(popupNode(place, lat, lon)).openPopup();
  }

  /**
   * Initialize or re-center the Leaflet map container.
   * @param {number} [initialLat] Initial map center latitude.
   * @param {number} [initialLon] Initial map center longitude.
   * @param {number} [zoom] Initial Leaflet zoom level.
   * @returns {void}
   */
  function initMap(initialLat = DEFAULT_VIEW.lat, initialLon = DEFAULT_VIEW.lon, zoom = DEFAULT_VIEW.zoom) {
    if (typeof L === "undefined" || !Dom.byId("map")) return;
    if (map) {
      map.setView([initialLat, initialLon], zoom);
      if (marker) marker.setLatLng([initialLat, initialLon]);
      return;
    }
    map = L.map("map", {zoomControl: true}).setView([initialLat, initialLon], zoom);
    L.tileLayer(TILE_URL, {maxZoom: 19, attribution: TILE_ATTR}).addTo(map);
    map.on("click", (e) => {
      clearAccCircle();
      setExactLocation(e.latlng.lat, e.latlng.lng, null, true, true);
    });
    setTimeout(() => { if (map) map.invalidateSize(); }, 250);
  }

  /**
   * Persist the current non-coarse coordinates to localStorage.
   * @param {object} data Plan or coordinates metadata containing place name.
   * @returns {void}
   */
  function saveLocation(data) {
    if (!coords || !data || data.place === "Your location") return;
    if (coords.accuracy && coords.accuracy > Dom.CONFIG.COORD_ACCURACY_CAP_M) return;
    try {
      localStorage.setItem(Dom.CONFIG.STORAGE_KEY, JSON.stringify({
        lat: +coords.lat.toFixed(4), lon: +coords.lon.toFixed(4),
        place: coords.place || data.place, ts: Date.now(),
      }));
      ui.forgetBtn.hidden = false;
    } catch (_) {}
  }

  /**
   * Reverse-geocode coordinates unless a known place name was already supplied.
   * @param {number} lat Latitude coordinate.
   * @param {number} lon Longitude coordinate.
   * @param {string|null} knownPlace Optional pre-resolved label.
   * @param {number} seq Request sequence token to ignore stale responses.
   * @returns {Promise<{place: string, city: string}|null>} Resolved place details or null if superseded.
   */
  async function resolvePlace(lat, lon, knownPlace, seq) {
    if (knownPlace && knownPlace.toLowerCase() !== "your location") return {place: knownPlace, city: ""};
    try {
      const r = await fetch(`/api/locate?lat=${lat}&lon=${lon}`);
      if (r.ok) {
        const d = await r.json();
        if (seq !== locSeq) return null;
        if (d.place && d.place.toLowerCase() !== "your location") return {place: d.place, city: d.city || ""};
      }
    } catch (_) {}
    return seq === locSeq ? {place: `Lat ${lat.toFixed(2)}, Lon ${lon.toFixed(2)}`, city: ""} : null;
  }

  /**
   * Finalize state, UI status, marker, and optional plan submit for resolved coordinates.
   * @param {number} lat Latitude coordinate.
   * @param {number} lon Longitude coordinate.
   * @param {{place: string, city: string}} resolved Reverse-geocoded place result.
   * @param {boolean} shouldSubmit Whether to submit the plan form automatically.
   * @param {boolean} showDragHint Whether to display pin drag guidance.
   * @returns {void}
   */
  function finishExactLocation(lat, lon, resolved, shouldSubmit, showDragHint) {
    const city = Dom.cityFromPlace(resolved.place) || resolved.city || "";
    coords.place = resolved.place;
    ui.onLocationPicked(city);
    const hint = showDragHint ? " Drag the pin to adjust your exact spot." : "";
    ui.geoSt.textContent = `\uD83D\uDCCD Selected: ${resolved.place}.${hint}`;
    showMapCoords(lat, lon, resolved.place);
    placeMarker(lat, lon, resolved.place);
    saveLocation(coords);
    if (shouldSubmit) ui.form.requestSubmit();
  }

  /**
   * Select coordinates on the map, reverse-geocode, and optionally trigger a plan build.
   * @param {number} lat Latitude coordinate.
   * @param {number} lon Longitude coordinate.
   * @param {string|null} [knownPlace] Optional pre-resolved place label.
   * @param {boolean} [shouldSubmit] Whether to submit the plan form.
   * @param {boolean} [showDragHint] Whether to show pin adjustment guidance.
   * @returns {Promise<void>} Resolves once location selection completes.
   */
  async function setExactLocation(lat, lon, knownPlace = null, shouldSubmit = false, showDragHint = false) {
    lat = Number(lat); lon = Number(lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const seq = ++locSeq;
    coords = {lat, lon, isManualOrApprox: Boolean(showDragHint)};
    placeMarker(lat, lon, "Locating\u2026");
    if (map) {
      map.setView([lat, lon], Math.max(map.getZoom(), PICK_ZOOM));
      setTimeout(() => { if (map) map.invalidateSize(); }, 150);
    }
    showMapCoords(lat, lon, "resolving address\u2026");
    const resolved = await resolvePlace(lat, lon, knownPlace, seq);
    if (!resolved) return;
    finishExactLocation(lat, lon, resolved, shouldSubmit, showDragHint);
  }

  /**
   * Apply a validated saved location record onto the form and Leaflet map.
   * @param {{lat: number, lon: number, place: string}} v Saved location entry.
   * @returns {void}
   */
  function applySavedLocation(v) {
    coords = v;
    ui.cityIn.value = Dom.cityFromPlace(v.place);
    ui.geoSt.textContent = `Last used: ${v.place}. Use my location or search to change it.`;
    showMapCoords(v.lat, v.lon, v.place);
    ui.forgetBtn.hidden = false;
    initMap(v.lat, v.lon, PICK_ZOOM);
    placeMarker(v.lat, v.lon, v.place);
  }

  /**
   * Load non-expired saved location from localStorage or initialize default map view.
   * @returns {void}
   */
  function loadLocation() {
    try {
      const v = JSON.parse(localStorage.getItem(Dom.CONFIG.STORAGE_KEY) || "null");
      if (v && typeof root.CleanAirLocate !== "undefined" && root.CleanAirLocate.isSavedExpired(v)) {
        localStorage.removeItem(Dom.CONFIG.STORAGE_KEY);
      } else if (v && isValidSavedLocation(v)) {
        applySavedLocation(v);
        return;
      }
    } catch (_) {}
    initMap();
  }

  /**
   * Clear saved location from localStorage, form fields, and map overlays.
   * @returns {void}
   */
  function forgetLocation() {
    try { localStorage.removeItem(Dom.CONFIG.STORAGE_KEY); } catch (_) {}
    coords = null; ui.cityIn.value = ""; ui.forgetBtn.hidden = true;
    ui.geoSt.textContent = "Saved location removed.";
    if (ui.mapCoordsEl) ui.mapCoordsEl.textContent = "";
    clearAccCircle();
    if (marker && map) { map.removeLayer(marker); marker = null; }
    if (map) map.setView([DEFAULT_VIEW.lat, DEFAULT_VIEW.lon], DEFAULT_VIEW.zoom);
  }

  /**
   * Display accuracy circle on Leaflet map for a geolocation fix.
   * @param {{lat: number, lon: number, accuracy: number, quality: string}} fix Geolocation fix.
   * @returns {void}
   */
  function showAccuracyCircle(fix) {
    if (typeof L === "undefined" || !map) return;
    clearAccCircle();
    accCircle = L.circle([fix.lat, fix.lon], {radius: fix.accuracy, weight: 1}).addTo(map);
    map.fitBounds(accCircle.getBounds(), {maxZoom: fix.quality !== "coarse" ? FIT_MAX_GOOD : FIT_MAX_COARSE});
  }

  /**
   * Report coarse geolocation uncertainty without overwriting an existing pinned place.
   * @param {{lat: number, lon: number, accuracy: number}} fix Coarse geolocation fix.
   * @returns {void}
   */
  function reportCoarseFix(fix) {
    const a = root.CleanAirLocate.fmt(fix.accuracy);
    if (coords && coords.place) {
      ui.geoSt.textContent = `This device estimates you near the area shown (about ${a}). Keep ${coords.place}, or search your city or pincode to change it.`;
      return;
    }
    if (map) map.setView([fix.lat, fix.lon], COARSE_ZOOM);
    ui.geoSt.textContent = `This device estimates you near the area shown (about ${a}). Search your city or pincode to set the exact spot, or click the map.`;
  }

  /**
   * Detect the browser location with accuracy settling and update map and plan.
   * @returns {Promise<void>} Resolves when geolocation handling finishes.
   */
  async function useLocation() {
    ui.geoBtn.disabled = true; ui.geoSt.textContent = "Finding your location\u2026";
    try {
      const fix = await root.CleanAirLocate.detect({
        onProgress: (a) => { ui.geoSt.textContent = `Improving accuracy\u2026 currently about ${root.CleanAirLocate.fmt(a)}`; },
      });
      showAccuracyCircle(fix);
      if (fix.quality === "coarse") { reportCoarseFix(fix); return; }
      await setExactLocation(fix.lat, fix.lon, null, fix.quality !== "approximate", fix.quality === "approximate");
      const suffix = fix.quality === "approximate" ? " Drag the pin to adjust your exact spot." : "";
      ui.geoSt.textContent = root.CleanAirLocate.describe(fix) + suffix;
    } catch (e) {
      ui.geoSt.textContent = e.message || "Could not get your location. Search your city instead.";
    } finally { ui.geoBtn.disabled = false; }
  }

  /**
   * Bind button listeners, load persisted state, and initialize map module.
   * @param {object} refs UI element and callback references.
   * @returns {void}
   */
  function init(refs) {
    ui = refs;
    ui.geoBtn.addEventListener("click", useLocation);
    ui.forgetBtn.addEventListener("click", forgetLocation);
    loadLocation();
    window.addEventListener("load", () => { setTimeout(() => { if (map) map.invalidateSize(); }, 300); });
  }

  const api = {
    init, clearAccCircle, setExactLocation, saveLocation, formatCoordsLine, isValidSavedLocation,
    getCoords: () => coords, clearCoords: () => { coords = null; },
  };
  root.CleanAirMap = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
