"use strict";
/* Image reading, Google Search advisories, follow-up chat, and OSM nearby help panels. */
(function (root) {
  const Dom = root.CleanAirDom || (typeof require !== "undefined" ? require("./dom.js") : null);
  const METRES_PER_KM = 1000;

  let ctx = null, ctxCoords = null, history = [], ui = {};

  /**
   * Validate an uploaded or pasted image file's MIME type and size.
   * @param {File|null|undefined} file Candidate File object.
   * @returns {string|null} Validation error message or null when valid.
   */
  function validateImageFile(file) {
    if (!file) return null;
    if (!Dom.CONFIG.ALLOWED_IMAGE_RE.test(file.type)) return "Use a PNG, JPEG or WebP image.";
    if (file.size > Dom.CONFIG.MAX_IMAGE_BYTES) return "Image must be under 3 MB.";
    return null;
  }

  /**
   * Format distance in metres or kilometres.
   * @param {number} meters Distance in metres.
   * @returns {string} Human-readable distance label.
   */
  function formatDistance(meters) {
    return meters < METRES_PER_KM ? `${Math.round(meters)} m` : `${(meters / METRES_PER_KM).toFixed(1)} km`;
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
    const errMsg = validateImageFile(file);
    if (errMsg) { st.textContent = errMsg; return; }
    st.textContent = "AI is reading the image\u2026";
    try {
      const b64 = await readFileAsBase64(file);
      const data = await Dom.postJson("/api/image-aqi", {image: b64, mime: file.type});
      if (data.aqi !== null) {
        ui.onImageAqi(data.aqi);
        st.textContent = `AQI ${data.aqi} found. ${data.note}`;
      } else {
        st.textContent = `No AQI number found. Visibility: ${data.visibility}. Please type the AQI.`;
      }
    } catch (err) { st.textContent = err.message; }
  }

  /**
   * Fetch Google Search grounded official air advisories for the current city.
   * @returns {Promise<void>} Resolves once advisory output renders.
   */
  async function checkAdvisory() {
    const box = ui.advOut;
    const city = (ctx?.place && !Dom.isCoordLabel(ctx.place) ? ctx.place : (ui.cityIn.value || "")).trim();
    if (!city) { box.replaceChildren(Dom.el("p", "Enter a city above first.", "err")); return; }
    box.replaceChildren(Dom.el("div", undefined, "skel"));
    try {
      const data = await Dom.postJson("/api/advisory", {city, lang: ctx?.lang || "en"});
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
      ui.chatLog.append(Dom.el("p", data.answer));
      history.push({role: "user", text: q}, {role: "assistant", text: data.answer});
    } catch (err) { ui.chatLog.append(Dom.el("p", err.message, "err")); }
    finally { ui.qBtn.disabled = false; }
  }

  /**
   * Render nearby clean-air venues and OpenStreetMap attribution inside box.
   * @param {HTMLElement} box Target container element.
   * @param {{places?: Array<object>, stale?: boolean}} data Nearby API response payload.
   * @returns {void}
   */
  function renderNearbyList(box, data) {
    const places = data.places || [];
    if (!places.length) {
      box.replaceChildren(Dom.el("p", "No places found within 4 km. Try searching a nearby larger city.", "help"));
      return;
    }
    box.replaceChildren();
    if (data.stale) {
      box.append(Dom.el("p", "Showing results from earlier today because the public map servers are busy.", "help"));
    }
    places.forEach((p) => {
      const pEl = Dom.el("p", undefined, "src");
      pEl.append(Dom.el("span", `${p.name} \u00b7 ${p.category} \u00b7 ${formatDistance(p.distance_m)} `));
      if (p.url && p.url.startsWith("https://")) {
        pEl.append(Dom.externalLink("OpenStreetMap", p.url));
      }
      box.append(pEl);
    });
    box.append(Dom.el("p", "Data \u00a9 OpenStreetMap contributors. Opening hours, mask stock and indoor air quality are not verified: call ahead.", "help"));
  }

  /**
   * Request nearby OpenStreetMap places for active coordinates and display results or fallback link.
   * @returns {Promise<void>} Resolves once nearby UI updates.
   */
  async function loadNearby() {
    const box = ui.nearOut;
    if (!ctxCoords) {
      box.replaceChildren(Dom.el("p", "Use my location, or pick a city from the suggestions, then build your plan first.", "err"));
      return;
    }
    box.replaceChildren(Dom.el("p", "Searching nearby places\u2026 this can take up to 30 seconds.", "help"), Dom.el("div", undefined, "skel"));
    try {
      const data = await Dom.postJson("/api/nearby", {lat: ctxCoords.lat, lon: ctxCoords.lon, lang: ctx?.lang || "en"});
      renderNearbyList(box, data);
    } catch (err) {
      box.replaceChildren(Dom.el("p", err.message, "err"));
      if (err.data?.map_url?.startsWith("https://")) box.append(Dom.createLinkParagraph("Open this area on OpenStreetMap", err.data.map_url));
      const retry = Dom.el("button", "Try again", "ghost");
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

  const api = {init, resetContext, validateImageFile, formatDistance};
  root.CleanAirExtras = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
