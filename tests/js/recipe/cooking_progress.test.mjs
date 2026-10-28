import test from 'node:test';
import assert from 'node:assert/strict';
import {
  clearCookingProgress,
  restoreCookingProgress,
  saveCookingProgress,
} from '../../../apps/recipe/static/recipe/cooking_progress.mjs';

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
  const fingerprint = 'recipe-content-v1';

  assert.equal(saveCookingProgress(storage, 'recipe-1', 2, [true, false], fingerprint), true);
  assert.deepEqual(restoreCookingProgress(storage, 'recipe-1', 4, 2, fingerprint), {
    step: 2,
    checked: [true, false],
  });
});

test('invalid or incompatible saved progress is ignored', () => {
  const storage = createStorage({
    badJson: '{',
    invalidStep: JSON.stringify({step: 4, checked: [true], recipeFingerprint: 'v1'}),
    changedIngredients: JSON.stringify({step: 1, checked: [true], recipeFingerprint: 'v1'}),
    invalidChecks: JSON.stringify({step: 1, checked: [1, false], recipeFingerprint: 'v1'}),
  });

  assert.equal(restoreCookingProgress(storage, 'badJson', 4, 1, 'v1'), null);
  assert.equal(restoreCookingProgress(storage, 'invalidStep', 4, 1, 'v1'), null);
  assert.equal(restoreCookingProgress(storage, 'changedIngredients', 4, 2, 'v1'), null);
  assert.equal(restoreCookingProgress(storage, 'invalidChecks', 4, 2, 'v1'), null);
});

test('progress is not restored after recipe steps or ingredient quantities change', () => {
  const storage = createStorage();
  saveCookingProgress(storage, 'recipe-1', 1, [true], 'old-recipe-content');

  assert.equal(restoreCookingProgress(storage, 'recipe-1', 3, 1, 'updated-recipe-content'), null);
});

test('storage failures do not prevent cooking mode from operating', () => {
  const unavailable = {
    getItem() { throw new Error('blocked'); },
    setItem() { throw new Error('blocked'); },
    removeItem() { throw new Error('blocked'); },
  };

  assert.equal(restoreCookingProgress(unavailable, 'recipe-1', 2, 1, 'v1'), null);
  assert.equal(saveCookingProgress(unavailable, 'recipe-1', 0, [false], 'v1'), false);
  assert.doesNotThrow(() => clearCookingProgress(unavailable, 'recipe-1'));
});

test('clearing progress removes only the matching recipe and portion entry', () => {
  const storage = createStorage({first: '{}', second: '{}'});

  clearCookingProgress(storage, 'first');

  assert.equal(storage.getItem('first'), null);
  assert.equal(storage.getItem('second'), '{}');
});
