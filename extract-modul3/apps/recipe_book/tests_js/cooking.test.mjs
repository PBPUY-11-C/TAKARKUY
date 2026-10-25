import assert from 'node:assert/strict';
import test from 'node:test';
import { cookingPayload, manualValues } from '../static/recipe_book/cooking.mjs';

const fields = {servings: {value: '2'}, include_staples: {checked: false},
  allow_unknown_expiry: {checked: true}};
test('independent cooking uses selected portions and explicit consent', () => {
  assert.deepEqual(cookingPayload({code: 'RECIPE'}, fields, []), {
    recipe_code: 'RECIPE', servings: 2, include_staples: false, allow_unknown_expiry: true, manual: []});
});
test('planned cooking sends required plan version and slot identity', () => {
  const payload = cookingPayload({code: 'RECIPE', slot: '4', version: '7'}, fields, []);
  assert.equal(payload.planned_meal, 4); assert.equal(payload.version, 7);
});
test('empty manual rows are omitted; partial rows are rejected', () => {
  const row = (quantity, grams) => ({dataset: {id: '3', version: '2'},
    querySelector: selector => ({value: selector.includes('quantity') ? quantity : grams})});
  assert.deepEqual(manualValues({children: [row('', '')]}), []);
  assert.throws(() => manualValues({children: [row('1', '')]}), /jumlah dan berat/);
  assert.deepEqual(manualValues({children: [row('1', '100')]}), [
    {batch_id: 3, version: 2, quantity: '1', grams_per_unit: '100'}]);
});
