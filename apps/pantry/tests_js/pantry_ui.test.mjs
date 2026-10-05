import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {runInNewContext} from "node:vm";
import {createActionKeyStore, locationExpiry, isAISuggestion, correctionConsent} from "../static/pantry/batch_actions.mjs";
import {storagePreview} from "../static/pantry/storage_preview.mjs";

const script = readFileSync(new URL("../static/pantry/pantry.js", import.meta.url), "utf8").replace(/^import .*;\n/gm, "");
class Element {
  constructor() { this.listeners = {}; this.dataset = {}; this.value = ""; this.textContent = ""; this.hidden = false; this.disabled = false; this.children = []; this.classList = {toggle() {}}; this.controls = new Map(); }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  append(...children) { for (const child of children) { child.parentElement = this; this.children.push(child); } }
  setAttribute() {}
  async trigger(name = "click") { return this.listeners[name]?.({currentTarget: this}); }
  querySelector(selector) { const found = this.querySelectorAll(selector)[0]; if (found) return found; if (!this.controls.has(selector)) this.controls.set(selector, new Element()); return this.controls.get(selector); }
  querySelectorAll(selector) {
    const descendants = this.children.flatMap(child => child instanceof Element ? [child, ...child.querySelectorAll("*")] : []);
    return descendants.filter(child => selector === "*" ||
      (selector === "tr[data-draft]" && "draft" in child.dataset) ||
      (selector === "[data-field]" && "field" in child.dataset) ||
      (selector === "input, select" && (child.type || child.dataset.field)) ||
      (selector.startsWith(".") && child.className === selector.slice(1)) ||
      (selector.startsWith('[data-field="') && child.dataset.field === selector.slice(13, -2)));
  }
  checkValidity() { return true; }
  replaceChildren(...children) { this.children = children; }
  remove() { this.removed = true; }
}
function setup({scan = false} = {}) {
  const elements = new Map();
  const get = (id) => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const row = new Element();
  row.dataset = {pantryItem: "1", version: "1"};
  for (const [selector, value] of Object.entries({"[data-pantry-location]": "suhu_ruang", "[data-pantry-expiry]": "2026-10-06", "[data-expiry-source]": "manual", "[data-edit-name]": "Bayam", "[data-edit-quantity]": "100", "[data-edit-unit]": "g", "[data-edit-category]": "sayur_buah", "[data-edit-ingredient]": "ING-BAYAM"})) row.querySelector(selector).value = value;
  get("pantry-storage-data").textContent = JSON.stringify({1: {options: {freezer: {estimated_expires_on: "2026-10-20", message: "Estimasi"}}}});
  const requests = [];
  get("receipt-file").dataset.geminiFallback = scan ? "true" : "false";
  get("receipt-file").files = [{type: "image/jpeg", size: 10, name: "receipt.jpg"}];
  get("ocr-unit-options").options = [];
  let next = {ok: true, data: {version: 2, location: "suhu_ruang", expiry_source: "manual", estimated_expires_on: "2026-10-06", message: "Tersimpan"}};
  const context = {createActionKeyStore, locationExpiry, isAISuggestion, correctionConsent, storagePreview, needsGeminiFallback: () => true, parseReceiptText: () => [{name: "BYM", quantity: 1, unit: "g"}], URL: {createObjectURL: () => "blob:test", revokeObjectURL() {}}, crypto: {randomUUID: () => `key-${requests.length}`},
    document: {getElementById: get, createElement: () => new Element(), createTextNode: text => ({textContent: text}), querySelector: () => ({value: "csrf"}), querySelectorAll: () => row.removed ? [] : [row]},
    window: {Tesseract: {createWorker: async () => ({recognize: async () => ({data: {text: "BYM", confidence: 50}})})}, addEventListener() {}, confirm: () => true, location: {reload() {}}},
    fetch: async (url, options) => { requests.push({url, options}); return {ok: next.ok, json: async () => next.data}; },
  };
  runInNewContext(script, context);
  return {row, requests, get, context, response: (ok, data) => {next = {ok, data};}};
}

test("combined photo rows do not request name suggestions and keep raw for consent", () => {
  const app = setup();
  app.context.showDraftItems([{raw: "BYM", name: "Bayam", quantity: 1, unit: "g", ingredient_code: "ING-BAYAM", method: "ai_foto_perlu_periksa"}], {photoAttempted: true, photoSucceeded: true});
  assert.equal(app.requests.length, 0);
  const draft = app.get("draft-rows").children[0];
  assert.equal(draft.dataset.originalName, "BYM");
  assert.equal(draft.dataset.ingredientCode, "ING-BAYAM");
  assert.match(draft.querySelector(".name-suggestion").textContent, /dengan AI/);
});

test("photo failure or empty result only permits local name matching", async () => {
  const app = setup();
  app.response(true, {suggestions: []});
  app.context.showDraftItems([{name: "BYM", quantity: 1, unit: "g"}], {photoAttempted: true, photoSucceeded: false});
  await Promise.resolve();
  assert.equal(app.requests.length, 1);
  assert.equal(JSON.parse(app.requests[0].options.body).allow_llm, false);
});

test("actual low-confidence scan sends one photo, never a text-AI request afterwards", async () => {
  for (const outcome of ["success", "empty", "failure"]) {
    const app = setup({scan: true});
    app.response(outcome !== "failure", outcome === "success" ? {items: [{raw: "BYM", name: "Bayam", quantity: 1, unit: "g", ingredient_code: "ING-BAYAM", method: "ai_foto_perlu_periksa"}]} : {items: [], error: "Provider unavailable"});
    // readWithGemini uses FormData; this mock never transmits or stores images.
    app.context.FormData = class { append() {} };
    await app.get("receipt-file").trigger("change");
    assert.equal(app.requests.filter(request => request.url === "/modul2/ocr-fallback/").length, 1);
    const suggestions = app.requests.filter(request => request.url === "/modul2/suggestions/");
    if (outcome === "success") assert.equal(suggestions.length, 0);
    else {
      assert.equal(suggestions.length, 1);
      assert.equal(JSON.parse(suggestions[0].options.body).allow_llm, false);
    }
  }
});

test("pantry UI preserves a manual date when storage location changes", async () => {
  const app = setup();
  app.row.querySelector("[data-pantry-location]").value = "freezer";
  await app.row.querySelector("[data-pantry-location]").trigger("change");
  assert.equal(app.row.querySelector("[data-pantry-expiry]").value, "2026-10-06");
});

test("save sends version, full editable fields and retry-stable operation key", async () => {
  const app = setup();
  app.response(false, {error: "Muat ulang stok"});
  await app.row.querySelector(".save-pantry-details").trigger();
  await app.row.querySelector(".save-pantry-details").trigger();
  const first = JSON.parse(app.requests[0].options.body);
  const again = JSON.parse(app.requests[1].options.body);
  assert.equal(first.version, 1);
  assert.equal(first.quantity, "100");
  assert.equal(first.ingredient_code, "ING-BAYAM");
  assert.equal(first.operation_key, again.operation_key);
  assert.match(app.row.querySelector(".row-feedback").textContent, /Muat ulang/);
  assert.equal(app.row.dataset.version, "1");
  app.response(true, {version: 2, location: "freezer", expiry_source: "manual", estimated_expires_on: "2026-10-06", message: "Tersimpan"});
  await app.row.querySelector(".save-pantry-details").trigger();
  assert.equal(app.row.dataset.version, 2);
});

test("delete carries a version and key, and recipe names render as text", async () => {
  const app = setup();
  await app.row.querySelector(".delete-pantry-item").trigger();
  const body = JSON.parse(app.requests[0].options.body);
  assert.equal(body.version, 1);
  assert.ok(body.operation_key);
  assert.equal(app.row.removed, true);
  app.response(true, {recipes: [{name: "<script>unsafe</script>", complete: true}]});
  await app.get("stock-recipes-button").trigger();
  assert.match(app.get("stock-recipes-output").children[0].textContent, /<script>unsafe<\/script>/);
});

test("cached AI autofill has an AI label and saving does not imply confirmation", async () => {
  const app = setup();
  const draft = app.context.addDraftRow({name: "BYM", quantity: 1, unit: "g"});
  draft.isConnected = true;
  app.response(true, {suggestions: [{raw_name: "BYM", suggested_name: "Bayam", ingredient_code: "ING-BAYAM", method: "ai_cache_perlu_periksa"}]});
  await app.context.suggestRows([{name: "BYM"}], 0);
  assert.match(draft.querySelector(".name-suggestion").textContent, /dengan AI/);
  assert.equal(draft.querySelector(".confirm-name").checked, undefined);
  app.response(true, {saved: 1});
  await app.get("save-draft").trigger();
  const item = JSON.parse(app.requests.at(-1).options.body).items[0];
  assert.equal(item.name, "Bayam");
  assert.equal(item.accepted, false);
  assert.equal(item.user_edited, false);
  draft.querySelector(".confirm-name").checked = true;
  await app.get("save-draft").trigger();
  assert.equal(JSON.parse(app.requests.at(-1).options.body).items[0].accepted, true);
});

test("editing a suggested name clears old consent and sends actual edit metadata", async () => {
  const app = setup();
  const draft = app.context.addDraftRow({name: "BYM", quantity: 1, unit: "g"});
  draft.dataset.ingredientCode = "ING-BAYAM";
  draft.querySelector(".confirm-name").checked = true;
  draft.querySelector('[data-field="name"]').value = "Bayam";
  await draft.querySelector('[data-field="name"]').trigger("input");
  assert.equal(draft.querySelector(".confirm-name").checked, false);
  app.response(true, {saved: 1});
  await app.get("save-draft").trigger();
  const item = JSON.parse(app.requests.at(-1).options.body).items[0];
  assert.equal(item.user_edited, true);
  assert.equal(item.accepted, false);
  assert.equal(item.ingredient_code, undefined);
});
