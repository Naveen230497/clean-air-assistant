"use strict";
/* Image reading, Google Search advisories, follow-up chat, and OSM nearby help panels. */
(function (root) {
  const Dom = root.CleanAirDom || (typeof require !== "undefined" ? require("./dom.js") : null);
  const I18n = root.CleanAirI18n || (typeof require !== "undefined" ? require("./i18n.js") : null);
  const METRES_PER_KM = 1000;
  const NEARBY_CAT_KEYS = {
    "Hospital or clinic": "nearby_hospital",
    Pharmacy: "nearby_pharmacy",
    Library: "nearby_library",
    Mall: "nearby_mall",
  };

  let ctx = null, ctxCoords = null, history = [], ui = {};

  /**
   * Return the active normalized language code from context or language selector.
   * @returns {"en"|"hi"|"te"|"ta"|"bn"|"mr"} Active language code.
   */
  function activeLang() {
    const raw = (ctx && ctx.lang) || (ui.langSelect && ui.langSelect.value) || "en";
    return I18n ? I18n.normalizeLang(raw) : "en";
  }

  /**
   * Translate a UI message key using the active language.
   * @param {string} key Translation key.
   * @param {Record<string, string|number>} [params] Placeholder map.
   * @param {string} [lang] Optional explicit language override.
   * @returns {string} Localized label string.
   */
  function t(key, params, lang) {
    return I18n ? I18n.tr(lang || activeLang(), key, params) : "";
  }

  /**
   * Validate an uploaded or pasted image file's MIME type and size.
   * @param {File|null|undefined} file Candidate File object.
   * @param {string} [lang] Optional language code for error text.
   * @returns {string|null} Validation error message or null when valid.
   */
  function validateImageFile(file, lang) {
    if (!file) return null;
    if (!Dom.CONFIG.ALLOWED_IMAGE_RE.test(file.type)) return t("image_bad_type", undefined, lang);
    if (file.size > Dom.CONFIG.MAX_IMAGE_BYTES) return t("image_too_big", undefined, lang);
    return null;
  }

  /**
   * Format distance in metres or kilometres using localized unit labels.
   * @param {number} meters Distance in metres.
   * @param {string} [lang] Optional language code override.
   * @returns {string} Human-readable distance label.
   */
  function formatDistance(meters, lang) {
    const unit = meters < METRES_PER_KM ? (t("unit_m", undefined, lang) || "m") : (t("unit_km", undefined, lang) || "km");
    const val = meters < METRES_PER_KM ? Math.round(meters) : (meters / METRES_PER_KM).toFixed(1);
    return `${val} ${unit}`;
  }

  /**
   * Translate a known nearby venue category label into the active language.
   * @param {string|null|undefined} category Canonical or pre-localized venue category.
   * @param {string} [lang] Optional language code override.
   * @returns {string} Localized category label or original fallback string.
   */
  function translateCategory(category, lang) {
    const key = Object.hasOwn(NEARBY_CAT_KEYS, category) ? NEARBY_CAT_KEYS[category] : "";
    return (key && t(key, undefined, lang)) || String(category || "");
  }

  /**
   * Read an image File as a base64 string without data URL prefix.
   * @param {File} file Image file to encode.
   * @returns {Promise<string>} Base64-encoded image payload.
   */
  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  /**
   * Upload an image to /api/image-aqi and populate the AQI field when found.
   * @param {File|undefined} file Selected or pasted image file.
   * @returns {Promise<void>} Resolves once upload handling finishes.
   */
  async function readImage(file) {
    const st = ui.photoStatus;
    if (!file) return;
    st.setAttribute("lang", activeLang());
    const errMsg = validateImageFile(file, activeLang());
    if (errMsg) { st.textContent = errMsg; return; }
    st.textContent = t("image_reading");
    try {
      const b64 = await readFileAsBase64(file);
      const data = await Dom.postJson("/api/image-aqi", {image: b64, mime: file.type});
      if (data.aqi !== null) {
        ui.onImageAqi(data.aqi);
        st.textContent = t("image_found", {aqi: data.aqi, note: data.note});
      } else {
        st.textContent = t("image_no_num", {vis: data.visibility});
      }
    } catch (err) { st.textContent = err.message; }
  }

  /**
   * Fetch Google Search grounded official air advisories for the current city.
   * @returns {Promise<void>} Resolves once advisory output renders.
   */
  async function checkAdvisory() {
    const box = ui.advOut;
    box.setAttribute("lang", activeLang());
    const city = (ctx?.place && !Dom.isCoordLabel(ctx.place) ? ctx.place : (ui.cityIn.value || "")).trim();
    if (!city) { box.replaceChildren(Dom.el("p", t("enter_city"), "err")); return; }
    box.replaceChildren(Dom.el("div", undefined, "skel"));
    try {
      const data = await Dom.postJson("/api/advisory", {city, lang: activeLang()});
      box.replaceChildren(Dom.el("p", data.text));
      data.sources.forEach((s) => box.append(Dom.createLinkParagraph(s.title, s.url)));
    } catch (err) { box.replaceChildren(Dom.el("p", err.message, "err")); }
  }

  /**
   * Submit a follow-up chat question grounded in current place and AQI context.
   * @param {Event} e Form submit event.
   * @returns {Promise<void>} Resolves when reply or error renders.
   */
  async function submitChat(e) {
    e.preventDefault();
    const q = ui.qInput.value.trim();
    if (!q || !ctx) return;
    ui.chatLog.append(Dom.el("p", q, "me"));
    ui.qInput.value = "";
    ui.qBtn.disabled = true;
    try {
      const data = await Dom.postJson("/api/chat", {
        question: q, history: history.slice(-Dom.CONFIG.MAX_HISTORY),
        aqi: ctx.aqi, place: ctx.place, lang: ctx.lang,
      });
      const reply = Dom.el("p", data.answer);
      reply.setAttribute("lang", activeLang());
      ui.chatLog.append(reply);
      history.push({role: "user", text: q}, {role: "assistant", text: data.answer});
    } catch (err) {
      const errNode = Dom.el("p", err.message, "err");
      errNode.setAttribute("lang", activeLang());
      ui.chatLog.append(errNode);
    } finally { ui.qBtn.disabled = false; }
  }

  /**
   * Render nearby clean-air venues and OpenStreetMap attribution inside box.
   * @param {HTMLElement} box Target container element.
   * @param {{places?: Array<object>, stale?: boolean}} data Nearby API response payload.
   * @returns {void}
   */
  function renderNearbyList(box, data) {
    const places = data.places || [];
    box.setAttribute("lang", activeLang());
    if (!places.length) {
      box.replaceChildren(Dom.el("p", t("no_places"), "help"));
      return;
    }
    box.replaceChildren();
    if (data.stale) box.append(Dom.el("p", t("stale_places"), "help"));
    places.forEach((p) => {
      const pEl = Dom.el("p", undefined, "src");
      const cat = translateCategory(p.category);
      pEl.append(Dom.el("span", `${p.name} \u00b7 ${cat} \u00b7 ${formatDistance(p.distance_m)} `));
      if (p.url && p.url.startsWith("https://")) pEl.append(Dom.externalLink("OpenStreetMap", p.url));
      box.append(pEl);
    });
    box.append(Dom.el("p", t("osm_attr"), "help"));
  }

  /**
   * Request nearby OpenStreetMap places for active coordinates and display results or fallback link.
   * @returns {Promise<void>} Resolves once nearby UI updates.
   */
  async function loadNearby() {
    const box = ui.nearOut;
    box.setAttribute("lang", activeLang());
    if (!ctxCoords) {
      box.replaceChildren(Dom.el("p", t("need_coords"), "err"));
      return;
    }
    box.replaceChildren(Dom.el("p", t("searching_nearby"), "help"), Dom.el("div", undefined, "skel"));
    try {
      const data = await Dom.postJson("/api/nearby", {lat: ctxCoords.lat, lon: ctxCoords.lon, lang: activeLang()});
      renderNearbyList(box, data);
    } catch (err) {
      box.replaceChildren(Dom.el("p", err.message, "err"));
      if (err.data?.map_url?.startsWith("https://")) box.append(Dom.createLinkParagraph(t("osm_open"), err.data.map_url));
      const retry = Dom.el("button", t("try_again"), "ghost");
      retry.type = "button";
      retry.addEventListener("click", loadNearby);
      box.append(retry);
    }
  }

  /**
   * Reset chat history and secondary cards for a newly built plan context.
   * @param {{aqi: number, place: string, lang: string}} nextCtx Active plan context.
   * @param {{lat: number, lon: number}|null} nextCoords Active rounded coordinates or null.
   * @returns {void}
   */
  function resetContext(nextCtx, nextCoords) {
    ctx = nextCtx; ctxCoords = nextCoords; history = [];
    ui.chatLog.replaceChildren(); ui.advOut.replaceChildren(); ui.nearOut.replaceChildren();
    ui.extrasSection.hidden = false;
  }

  /**
   * Attach event listeners for photo drop/paste, advisory lookup, chat, and nearby help.
   * @param {object} refs UI element and callback references.
   * @returns {void}
   */
  function init(refs) {
    ui = refs;
    ui.photoInput.addEventListener("change", (e) => readImage(e.target.files[0]));
    ui.cameraInput.addEventListener("change", (e) => readImage(e.target.files[0]));
    ["dragenter", "dragover"].forEach((t) => ui.drop.addEventListener(t, (e) => { e.preventDefault(); ui.drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((t) => ui.drop.addEventListener(t, (e) => { e.preventDefault(); ui.drop.classList.remove("over"); }));
    ui.drop.addEventListener("drop", (e) => readImage(e.dataTransfer.files[0]));
    document.addEventListener("paste", (e) => {
      const file = [...(e.clipboardData?.files || [])].find((x) => x.type.startsWith("image/"));
      if (file) readImage(file);
    });
    ui.advBtn.addEventListener("click", checkAdvisory);
    ui.chatForm.addEventListener("submit", submitChat);
    ui.nearBtn.addEventListener("click", loadNearby);
  }

  const api = {init, resetContext, validateImageFile, formatDistance, translateCategory, renderNearbyList};
  root.CleanAirExtras = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
