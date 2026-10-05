import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const script = readFileSync(new URL("../static/budget_planner/plans.js", import.meta.url), "utf8");

class Element {
  constructor() {
    this.listeners = {};
    this.children = [];
    this.dataset = {};
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.open = false;
    this.textContent = "";
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  async trigger(name = "click", event = {}) { return this.listeners[name]?.(event); }
  replaceChildren() { this.children = []; this.value = ""; }
  append(child) { this.children.push(child); if (!this.value && child.value) this.value = child.value; }
  showModal() { this.open = true; }
  close() { this.open = false; this.listeners.close?.(); }
}

function setup(overBudget = 5000) {
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const replace = new Element();
  replace.dataset = { alternativesUrl: "/alternatives/", previewUrl: "/preview/", day: "1", meal: "sarapan", version: "1" };
  const regenerate = new Element();
  regenerate.dataset = { previewUrl: "/preview/", version: "1" };
  const close = new Element();
  const requests = [];
  const redirects = [];
  const proposal = { id: "server-preview", apply_url: "/apply/", before: 10000, after: 15000,
    delta: 5000, budget: overBudget ? 10000 : 20000, over_budget: overBudget,
    days: 1, servings: 1, schedule: [{ number: 1, meals: [{ label: "Pagi", name: "Menu B" }],
      protein: 10, calories: 100 }], nutrition: {},
    shopping_groups: [{ items: [{ name: "<script>test</script>", quantity: "100", cost: 15000 }] }] };
  const context = {
    URL, document: {
      getElementById: (id) => id === "pending-plan-preview" ? null : get(id),
      createElement: () => new Element(),
      querySelector: () => ({ value: "test-csrf" }),
      querySelectorAll: (selector) => selector === "[data-replace-menu]" ? [replace]
        : selector === "[data-regenerate]" ? [regenerate]
        : selector === "[data-close-dialog]" ? [close] : [],
    },
    window: { location: { origin: "http://localhost", assign: (url) => redirects.push(url) } },
    fetch: async (url, options) => {
      requests.push({ url: String(url), options });
      return { ok: true, json: async () => options.method
        ? (String(url) === "/apply/" ? { url: "/modul1/?plan=draft" } : proposal)
        : { version: 1, recipes: [{ recipe_code: "B", name: "Menu B" }] } };
    },
  };
  runInNewContext(script, context);
  return { get, replace, regenerate, close, requests, redirects, context, proposal };
}

test("replacement waits for preview and explicit budget approval before applying", async () => {
  const app = setup();
  await app.replace.trigger();
  assert.equal(app.requests.length, 1);
  assert.equal(app.requests[0].options.method, undefined);
  await app.get("request-preview").trigger();
  assert.equal(app.requests.length, 2);
  assert.deepEqual(JSON.parse(app.requests[1].options.body), { action: "replace", version: 1,
    day: 1, meal: "sarapan", recipe: "B" });
  assert.match(app.get("preview-cost").textContent, /Naik/);
  assert.match(app.get("preview-budget").textContent, /Melebihi budget/);
  assert.equal(app.get("budget-increase").hidden, false);
  assert.equal(app.redirects.length, 0);
  app.get("new-budget").value = "16000";
  await app.get("apply-preview").trigger();
  assert.deepEqual(JSON.parse(app.requests[2].options.body), { new_budget: "16000" });
  assert.equal(app.requests[2].options.headers["X-CSRFToken"], "test-csrf");
  assert.deepEqual(app.redirects, ["/modul1/?plan=draft"]);
});

test("within-budget preview applies without changing the budget", async () => {
  const app = setup(0);
  await app.regenerate.trigger();
  assert.equal(app.get("budget-increase").hidden, true);
  await app.get("apply-preview").trigger();
  assert.deepEqual(JSON.parse(app.requests[1].options.body), {});
});

test("preview explains relaxed preferences and only shows targeted daily nutrition", async () => {
  const app = setup(0);
  app.proposal.preference_notes = ["Preferensi 60% dilonggarkan."];
  await app.regenerate.trigger();
  assert.match(app.get("preview-notes").textContent, /60%/);
  assert.doesNotMatch(app.get("preview-schedule").children[0].textContent, /protein/);
  app.proposal.nutrition_targets_set = true;
  await app.regenerate.trigger();
  assert.match(app.get("preview-schedule").children[0].textContent, /10 g protein/);
});

test("changing selected replacement invalidates the previous proposal", async () => {
  const app = setup();
  await app.replace.trigger();
  await app.get("request-preview").trigger();
  await app.get("replacement-recipe").trigger("change");
  assert.equal(app.get("preview-result").hidden, true);
  await app.get("apply-preview").trigger();
  assert.equal(app.requests.length, 2);
});

test("closing during alternatives fetch ignores the late response", async () => {
  const app = setup();
  let finish;
  app.context.fetch = () => new Promise((resolve) => { finish = resolve; });
  const pending = app.replace.trigger();
  await app.close.trigger();
  finish({ ok: true, json: async () => ({ version: 1, recipes: [{ recipe_code: "B", name: "B" }] }) });
  await pending;
  assert.equal(app.get("plan-dialog").open, false);
  assert.equal(app.get("replacement-picker").hidden, true);
});

test("closing during regeneration prevents applying the late proposal", async () => {
  const app = setup();
  let finish;
  app.context.fetch = () => new Promise((resolve) => { finish = resolve; });
  const pending = app.regenerate.trigger();
  await app.close.trigger();
  finish({ ok: true, json: async () => app.proposal });
  await pending;
  assert.equal(app.get("preview-result").hidden, true);
  await app.get("apply-preview").trigger();
  assert.equal(app.redirects.length, 0);
});

test("receipt/ingredient names render as plain text, not HTML", async () => {
  const app = setup();
  await app.regenerate.trigger();
  assert.match(app.get("preview-shopping").children[0].textContent, /<script>test<\/script>/);
  assert.equal(app.get("preview-shopping").children[0].innerHTML, undefined);
});
