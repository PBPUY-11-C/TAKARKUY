import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const script = readFileSync(new URL('../static/recipe_book/image_fallback.js', import.meta.url), 'utf8');

class Element {
  constructor(tag = 'img') {
    this.tagName = tag;
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.children = [];
    this.complete = false;
    this.naturalWidth = 100;
    this.alt = '';
    this.className = '';
  }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  append(child) { this.children.push(child); }
  closest() { return null; }
  replaceWith(replacement) { this.replacement = replacement; }
  triggerError() { this.listeners.error?.(); }
}

function setup(imagesBySelector) {
  runInNewContext(script, {
    document: {
      querySelectorAll: selector => imagesBySelector[selector] || [],
      createElement: tag => new Element(tag),
    },
  });
}

test('failed curated recipe image becomes an accessible placeholder and keeps the credit caption', () => {
  const image = new Element();
  image.alt = 'Foto Ayam Bakar Padang';
  setup({'.recipe-photo-image': [image]});
  image.triggerError();
  assert.equal(image.replacement.className, 'recipe-photo-placeholder');
  assert.equal(image.replacement.attributes.role, 'img');
  assert.equal(image.replacement.attributes['aria-label'], 'Foto Ayam Bakar Padang tidak dapat dimuat');
  assert.equal(image.replacement.children[1].textContent, 'Foto tidak dapat dimuat');
});

test('failed list and planner images use their existing layout placeholders', () => {
  const card = new Element();
  const planner = new Element();
  planner.alt = 'Foto Sup Tahu';
  setup({'.recipe-card-photo': [card], '.meal-photo': [planner]});
  card.triggerError();
  planner.triggerError();
  assert.equal(card.replacement.className, 'recipe-card-photo-placeholder');
  assert.equal(planner.replacement.className, 'meal-photo-placeholder');
  assert.equal(planner.replacement.attributes['aria-label'], 'Foto Sup Tahu tidak dapat dimuat');
});

test('already failed image is replaced when deferred fallback script initializes', () => {
  const image = new Element();
  image.alt = 'Foto Gulai';
  image.complete = true;
  image.naturalWidth = 0;
  setup({'.recipe-photo-image': [image]});
  assert.equal(image.replacement.className, 'recipe-photo-placeholder');
  image.triggerError();
  assert.equal(image.replacement.className, 'recipe-photo-placeholder');
});
