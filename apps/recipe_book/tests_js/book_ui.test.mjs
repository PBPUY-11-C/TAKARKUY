import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import { cookingPayload, manualValues } from '../static/recipe_book/cooking.mjs';

const script = readFileSync(new URL('../static/recipe_book/book.js', import.meta.url), 'utf8').replace(/^import .*;\n/, '');
class Element {
  constructor() { this.dataset = {}; this.children = []; this.listeners = {}; this.controls = new Map(); this.value = ''; this.disabled = false; }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  async trigger(type = 'click') { await this.listeners[type]?.({preventDefault() {}}); }
  querySelector(key) { if (!this.controls.has(key)) this.controls.set(key, new Element()); return this.controls.get(key); }
  querySelectorAll() { return [this.querySelector('[type=submit]')]; }
  append(...elements) { this.children.push(...elements); }
  replaceChildren(...elements) { this.children = elements; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  getAttribute() { return 'false'; }
  set innerHTML(value) { throw new Error(`Unsafe HTML: ${value}`); }
}
function setup() {
  const elements = new Map();
  const get = selector => { if (!elements.has(selector)) elements.set(selector, new Element()); return elements.get(selector); };
  get('#recipe-detail').dataset = {code: 'TEST', servings: '2', previewUrl: '/modul4/preview/', cookUrl: '/modul4/cook/'};
  get('#cooking-form').elements = {servings: {value: '2'}, include_staples: {checked: false}, allow_unknown_expiry: {checked: false}};
  let next = {complete: true, ingredients: [], missing: [], batches: [], manual_batches: []};
  const requests = [];
  let key = 0;
  let reloads = 0;
  runInNewContext(script, {cookingPayload, manualValues,
    document: {querySelector: get, querySelectorAll: () => [], createElement: () => new Element()},
    crypto: {randomUUID: () => `key-${++key}`}, location: {reload: () => reloads++},
    fetch: async (url, options) => {
      requests.push({url, payload: JSON.parse(options.body)});
      if (next instanceof Error) throw next;
      return {ok: true, json: async () => next};
    }});
  return {get, requests, setNext: value => { next = value; }, reloads: () => reloads};
}
test('confirm only follows a complete preview; edits invalidate it', async () => {
  const ui = setup();
  ui.setNext({complete: false, ingredients: [{ingredient_code: 'B', name: 'Bayam'}], missing: [{ingredient_code: 'B', grams: '10'}], batches: [], manual_batches: []});
  await ui.get('#cooking-form').trigger('submit');
  await ui.get('#confirm-cooking').trigger();
  assert.equal(ui.requests.length, 1);
  ui.setNext({complete: true, ingredients: [], missing: [], batches: [], manual_batches: []});
  await ui.get('#cooking-form').trigger('submit');
  assert.equal(ui.get('#confirm-cooking').disabled, false);
  await ui.get('#cooking-form').trigger('input');
  await ui.get('#confirm-cooking').trigger();
  assert.equal(ui.requests.length, 2);
});
test('retry after a network error keeps the exact operation key', async () => {
  const ui = setup();
  await ui.get('#cooking-form').trigger('submit');
  ui.setNext(new Error('Network'));
  await ui.get('#confirm-cooking').trigger();
  await ui.get('#confirm-cooking').trigger();
  assert.equal(ui.requests[1].payload.operation_key, ui.requests[2].payload.operation_key);
  ui.setNext({history_id: 1});
  await ui.get('#confirm-cooking').trigger();
  assert.equal(ui.reloads(), 1);
});
test('recipe and stock names render as plain text', async () => {
  const ui = setup();
  ui.setNext({complete: true, ingredients: [], missing: [], manual_batches: [], batches: [
    {name: '<img onerror=alert(1)>', quantity: '1', unit: 'g', grams: '1'}]});
  await ui.get('#cooking-form').trigger('submit');
  assert.match(ui.get('#cooking-preview').children[1].textContent, /<img onerror/);
});
test('skip button sends the slot, plan version and target status', async () => {
  const ui = setup();
  Object.assign(ui.get('#recipe-detail').dataset, {slot: '7', version: '3'});
  ui.get('#slot-status').dataset = {url: '/modul4/slot-status/', status: 'skipped'};
  await ui.get('#slot-status').trigger();
  assert.deepEqual(ui.requests.at(-1), {url: '/modul4/slot-status/', payload: {planned_meal: 7, version: 3, status: 'skipped'}});
  assert.equal(ui.reloads(), 1);
});
