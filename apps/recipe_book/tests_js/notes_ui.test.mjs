import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const script = readFileSync(new URL('../static/recipe_book/notes.js', import.meta.url), 'utf8');

class Element {
  constructor() { this.dataset = {}; this.listeners = {}; this.disabled = false; this.value = ''; this.textContent = ''; this.elements = {}; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  querySelectorAll() { return [new Element(), new Element()]; }
}

function setup() {
  const elements = new Map();
  const get = selector => { if (!elements.has(selector)) elements.set(selector, new Element()); return elements.get(selector); };
  const form = get('#recipe-note-form');
  form.dataset = {url: '/modul4/note/', code: 'TEST'};
  form.elements.namedItem = name => name === 'content' ? field : null;
  const field = new Element();
  field.value = 'Tambahkan jeruk nipis';
  let calls = 0;
  runInNewContext(script, {
    document: {querySelector: get},
    window: {confirm: () => true},
    fetch: async (url, options) => {
      calls += 1;
      assert.equal(url, '/modul4/note/');
      assert.equal(options.headers['X-CSRFToken'], 'csrf-test');
      return {ok: true, json: async () => ({saved: JSON.parse(options.body).content.length > 0})};
    },
  });
  get('[name=csrfmiddlewaretoken]').value = 'csrf-test';
  return {form, field, status: get('#recipe-note-status'), clear: get('#clear-recipe-note'), calls: () => calls};
}

test('saves a private note through the authenticated JSON endpoint', async () => {
  const ui = setup();
  ui.form.listeners.submit({preventDefault() {}});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.calls(), 1);
  assert.equal(ui.status.textContent, 'Catatan pribadi tersimpan.');
});

test('clear action deletes the note and reports the result accessibly', async () => {
  const ui = setup();
  ui.clear.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.calls(), 1);
  assert.equal(ui.field.value, '');
  assert.equal(ui.status.textContent, 'Catatan pribadi dihapus.');
});
