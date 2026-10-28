import assert from 'node:assert/strict';
import test from 'node:test';
import {roundedAmount, scaleServings} from '../../../apps/recipe/static/recipe/servings.mjs';

test('scales recipe amounts up and down from the same base servings', () => {
  assert.equal(scaleServings('125', 2, 4), 250);
  assert.equal(scaleServings('125', 2, 1), 62.5);
});

test('rejects invalid servings and nonnumeric amounts', () => {
  assert.equal(scaleServings('100', 0, 2), null);
  assert.equal(scaleServings('100', 2, 11), null);
  assert.equal(scaleServings('unknown', 2, 4), null);
});

test('rounds displayed amounts without accumulating repeated scaling errors', () => {
  assert.equal(roundedAmount(scaleServings('100', 3, 2)), 66.7);
  assert.equal(roundedAmount(scaleServings('100', 3, 3)), 100);
});
