"use strict";
// Run with: node --test tests/ui.test.js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const Dom = require("../app/static/dom.js");
const I18n = require("../app/static/i18n.js");
const PlanView = require("../app/static/plan_view.js");
const MapLoc = require("../app/static/map_location.js");
const Search = require("../app/static/search_box.js");
const Extras = require("../app/static/extras.js");

test("Dom.cityFromPlace and isCoordLabel handle labels and coordinates", () => {
  assert.strictEqual(Dom.isCoordLabel("Lat 16.30, Lon 80.45"), true);
  assert.strictEqual(Dom.isCoordLabel("Guntur, India"), false);
  assert.strictEqual(Dom.cityFromPlace("Guntur, Andhra Pradesh, India"), "Guntur");
  assert.strictEqual(Dom.cityFromPlace("Your location"), "");
  assert.strictEqual(Dom.cityFromPlace("Lat 16.30, Lon 80.45"), "");
  assert.strictEqual(Dom.validPlaceName("Guntur, Andhra Pradesh"), true);
  assert.strictEqual(Dom.validPlaceName("São Paulo"), true);
  assert.strictEqual(Dom.validPlaceName("Zürich"), true);
  assert.strictEqual(Dom.validPlaceName("<script>"), false);
});

test("PlanView.computeGaugeArc bounds values to 0..500 arc", () => {
  const zero = PlanView.computeGaugeArc(0);
  const mid = PlanView.computeGaugeArc(250);
  const high = PlanView.computeGaugeArc(900);
  const neg = PlanView.computeGaugeArc(-10);
  const bad = PlanView.computeGaugeArc("bad");
  assert.strictEqual(zero.rounded, 0);
  assert.strictEqual(zero.filled, 0);
  assert.ok(Math.abs(mid.filled - mid.total / 2) < 1e-6);
  assert.strictEqual(high.rounded, 900);
  assert.strictEqual(high.filled, high.total);
  assert.strictEqual(neg.rounded, -10);
  assert.strictEqual(neg.filled, 0);
  assert.strictEqual(bad.rounded, 0);
  assert.strictEqual(bad.filled, 0);
});

test("PlanView.buildPayloadFromFields respects AQI > coords > city priority", () => {
  const baseFlags = {children: true, elderly: false, respiratory: false, has_purifier: false, outdoor_exercise: true};
  const imgPayload = PlanView.buildPayloadFromFields(
    {commute: "car", cooking: "gas", lang: "en", city: "Delhi", aqi: "210", flags: baseFlags},
    {lat: 28.6, lon: 77.2},
    true
  );
  assert.strictEqual(imgPayload.aqi, 210);
  assert.strictEqual(imgPayload.aqi_source, "image");
  assert.strictEqual(imgPayload.lat, undefined);

  const coordPayload = PlanView.buildPayloadFromFields(
    {commute: "car", cooking: "gas", lang: "hi", city: "Delhi", aqi: "", flags: baseFlags},
    {lat: 16.3, lon: 80.45, place: "Guntur"},
    false
  );
  assert.strictEqual(coordPayload.lat, 16.3);
  assert.strictEqual(coordPayload.city, undefined);

  const cityPayload = PlanView.buildPayloadFromFields(
    {commute: "car", cooking: "gas", lang: "te", city: " Guntur ", aqi: "", flags: baseFlags},
    null,
    false
  );
  assert.strictEqual(cityPayload.city, "Guntur");
});

test("MapLoc.isValidSavedLocation and formatCoordsLine enforce accuracy and name rules", () => {
  assert.strictEqual(MapLoc.isValidSavedLocation({lat: 16.3, lon: 80.45, place: "Guntur, India"}), true);
  assert.strictEqual(MapLoc.isValidSavedLocation({lat: 16.3, lon: 80.45, accuracy: 9000, place: "Guntur"}), false);
  assert.strictEqual(MapLoc.isValidSavedLocation({lat: 16.3, lon: 80.45, place: "Your location"}), false);
  assert.strictEqual(MapLoc.formatCoordsLine(16.3, 80.45, "Guntur"), "Lat: 16.3000, Lon: 80.4500 \u2014 Guntur");
});

test("Search.nextActiveIndex wraps around listbox options cleanly", () => {
  assert.strictEqual(Search.nextActiveIndex(-1, 3, 1), 0);
  assert.strictEqual(Search.nextActiveIndex(2, 3, 1), 0);
  assert.strictEqual(Search.nextActiveIndex(0, 3, -1), 2);
  assert.strictEqual(Search.nextActiveIndex(0, 0, 1), -1);
});

test("Extras.validateImageFile and formatDistance enforce type/size caps and distance formatting", () => {
  assert.strictEqual(Extras.validateImageFile({type: "image/png", size: 1024}), null);
  assert.strictEqual(Extras.validateImageFile({type: "image/gif", size: 1024}), "Use a PNG, JPEG or WebP image.");
  assert.strictEqual(
    Extras.validateImageFile({type: "image/webp", size: 4 * 1024 * 1024}),
    "Image must be under 3 MB."
  );
  assert.strictEqual(Extras.formatDistance(349.6), "350 m");
  assert.strictEqual(Extras.formatDistance(1460), "1.5 km");
});

function makeFakeNode(tagName, ns) {
  return {
    tagName: String(tagName).toLowerCase(),
    ns: ns || null,
    className: "",
    textContent: "",
    attrs: {},
    style: {},
    children: [],
    append(...nodes) {
      this.children.push(...nodes);
    },
    replaceChildren(...nodes) {
      this.children = [...nodes];
    },
    setAttribute(key, value) {
      this.attrs[key] = String(value);
    },
  };
}

function findNodes(node, pred, out = []) {
  if (!node || typeof node !== "object") return out;
  if (pred(node)) out.push(node);
  for (const child of node.children || []) findNodes(child, pred, out);
  return out;
}

test("PlanView.renderPlan adds sr-only text summaries next to gauge and meter and style.css defines .sr-only", () => {
  const css = fs.readFileSync(path.join(__dirname, "..", "app", "static", "style.css"), "utf8");
  assert.match(css, /\.sr-only\b[^}]*position:\s*absolute/i);
  assert.match(css, /\.sr-only\b[^}]*overflow:\s*hidden/i);

  const prevDoc = global.document;
  const prevRaf = global.requestAnimationFrame;
  global.document = {
    createElement: (tag) => makeFakeNode(tag),
    createElementNS: (ns, tag) => makeFakeNode(tag, ns),
  };
  global.requestAnimationFrame = (fn) => fn();
  try {
    const out = makeFakeNode("section");
    PlanView.renderPlan(
      out,
      {
        aqi: 180,
        level: 3,
        band: "Unhealthy",
        est_reduction_pct: 42,
        safety_note: "",
        actions: [],
        briefing: {headline: "Limit outdoor exertion", summary: "Use an N95 outdoors.", top_three: [], source: "rules"},
      },
      "Delhi, India"
    );
    const gauge = findNodes(out, (n) => n.tagName === "svg")[0];
    const meter = findNodes(out, (n) => (n.className || "").split(/\s+/).includes("meter"))[0];
    const srOnly = findNodes(out, (n) => (n.className || "").split(/\s+/).includes("sr-only"));
    assert.strictEqual(gauge.attrs.role, "img");
    assert.strictEqual(gauge.attrs["aria-label"], "AQI 180");
    assert.strictEqual(meter.attrs.role, "img");
    assert.strictEqual(meter.attrs["aria-label"], "Estimated exposure reduction 42 percent");
    assert.deepStrictEqual(
      srOnly.map((n) => n.textContent),
      ["US AQI 180 (Unhealthy)", "Estimated exposure reduction 42%"]
    );
  } finally {
    global.document = prevDoc;
    global.requestAnimationFrame = prevRaf;
  }
});

test("style.css overrides dark-mode foreground color on step badges and checked pills for WCAG contrast", () => {
  const css = fs.readFileSync(path.join(__dirname, "..", "app", "static", "style.css"), "utf8");
  const lightNIdx = css.indexOf(".n{");
  const lightCheckedIdx = css.indexOf(".opt input:checked+span,.chip input:checked+span{");
  const darkMatch = css.match(/@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*\.n,\.opt input:checked\+span,\.chip input:checked\+span\{color:#0b121b\}/);
  assert.ok(lightNIdx !== -1 && lightCheckedIdx !== -1);
  assert.ok(darkMatch, "expected dark-mode override rule for .n and checked pills");
  assert.ok(darkMatch.index > lightNIdx && darkMatch.index > lightCheckedIdx);
  assert.match(css, /\.opt>span,\.chip>span\{/);
});

test("CleanAirI18n covers all six languages with matching placeholders and safe English fallback", () => {
  const langs = ["en", "hi", "te", "ta", "bn", "mr"];
  assert.deepStrictEqual(Object.keys(I18n.PACKS).sort(), [...langs].sort());
  const enKeys = Object.keys(I18n.PACKS.en).sort();
  const placeholders = (s) => [...s.matchAll(/\{([a-zA-Z0-9_]+)\}/g)].map((m) => m[1]).sort();
  for (const lang of langs) {
    assert.deepStrictEqual(Object.keys(I18n.PACKS[lang]).sort(), enKeys);
    for (const key of enKeys) {
      assert.ok(I18n.PACKS[lang][key].trim().length > 0, `${lang}.${key} should be non-empty`);
      assert.deepStrictEqual(placeholders(I18n.PACKS[lang][key]), placeholders(I18n.PACKS.en[key]));
    }
  }
  assert.strictEqual(I18n.normalizeLang("xx"), "en");
  assert.strictEqual(I18n.tr("xx", "your_actions"), "Your actions");
  assert.strictEqual(I18n.tr("te", "missing_key"), "");
});

test("PlanView.renderPlan localizes dynamic UI labels and sets lang attribute cleanly", () => {
  const prevDoc = global.document;
  const prevRaf = global.requestAnimationFrame;
  global.document = {
    createElement: (tag) => makeFakeNode(tag),
    createElementNS: (ns, tag) => makeFakeNode(tag, ns),
  };
  global.requestAnimationFrame = (fn) => fn();
  try {
    const out = makeFakeNode("section");
    PlanView.renderPlan(
      out,
      {
        aqi: 210,
        level: 4,
        band: "చాలా హానికరం",
        lang: "te",
        est_reduction_pct: 55,
        safety_note: "",
        actions: [{category: "routine", title: "మాస్క్", why: "కారణం", impact: "తగ్గుదల"}],
        briefing: {headline: "గాలి నాణ్యత", summary: "సారాంశం", top_three: ["మాస్క్"], source: "rules"},
      },
      "Guntur"
    );
    assert.strictEqual(out.attrs.lang, "te");
    const srOnly = findNodes(out, (n) => (n.className || "").split(/\s+/).includes("sr-only"));
    assert.strictEqual(srOnly[0].textContent, "US AQI 210 (చాలా హానికరం)");
    assert.strictEqual(srOnly[1].textContent, "అంచనా కాలుష్య తగ్గింపు 55%");
    const headings = findNodes(out, (n) => n.tagName === "h2").map((n) => n.textContent);
    assert.ok(headings.includes("మీ చర్యలు"));
    const impactEl = findNodes(out, (n) => (n.className || "").split(/\s+/).includes("impact"))[0];
    assert.strictEqual(impactEl.textContent, "ప్రభావం: తగ్గుదల");
  } finally {
    global.document = prevDoc;
    global.requestAnimationFrame = prevRaf;
  }
});
