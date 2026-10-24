import test from 'node:test';
import assert from 'node:assert/strict';
import {
  clearCookingProgress,
  restoreCookingProgress,
  saveCookingProgress,
} from '../static/recipe_book/cooking_progress.mjs';

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
    values,
  };
}

test('cooking progress saves and restores the active step and ingredient checks', () => {
  const storage = createStorage();

  assert.equal(saveCookingProgress(storage, 'recipe-1', 2, [true, false]), true);
  assert.deepEqual(restoreCookingProgress(storage, 'recipe-1', 4, 2), {
    step: 2,
    checked: [true, false],
  });
});

test('invalid or incompatible saved progress is ignored', () => {
  const storage = createStorage({
    badJson: '{',
    invalidStep: JSON.stringify({step: 4, checked: [true]}),
    changedIngredients: JSON.stringify({step: 1, checked: [true]}),
    invalidChecks: JSON.stringify({step: 1, checked: [1, false]}),
  });

  assert.equal(restoreCookingProgress(storage, 'badJson', 4, 1), null);
  assert.equal(restoreCookingProgress(storage, 'invalidStep', 4, 1), null);
  assert.equal(restoreCookingProgress(storage, 'changedIngredients', 4, 2), null);
  assert.equal(restoreCookingProgress(storage, 'invalidChecks', 4, 2), null);
});

test('storage failures do not prevent cooking mode from operating', () => {
  const unavailable = {
    getItem() { throw new Error('blocked'); },
    setItem() { throw new Error('blocked'); },
    removeItem() { throw new Error('blocked'); },
  };

  assert.equal(restoreCookingProgress(unavailable, 'recipe-1', 2, 1), null);
  assert.equal(saveCookingProgress(unavailable, 'recipe-1', 0, [false]), false);
  assert.doesNotThrow(() => clearCookingProgress(unavailable, 'recipe-1'));
});

test('clearing progress removes only the matching recipe and portion entry', () => {
  const storage = createStorage({first: '{}', second: '{}'});

  clearCookingProgress(storage, 'first');

  assert.equal(storage.getItem('first'), null);
  assert.equal(storage.getItem('second'), '{}');
});
