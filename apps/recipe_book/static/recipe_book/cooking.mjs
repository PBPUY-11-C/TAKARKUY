export function cookingPayload(dataset, fields, manual) {
  const payload = {recipe_code: dataset.code, servings: Number(fields.servings.value),
    include_staples: fields.include_staples.checked,
    allow_unknown_expiry: fields.allow_unknown_expiry.checked, manual};
  if (dataset.slot) { payload.planned_meal = Number(dataset.slot); payload.version = Number(dataset.version); }
  return payload;
}
export function manualValues(container) {
  return [...container.children].flatMap(row => {
    const quantity = row.querySelector('[data-field=quantity]').value;
    const weight = row.querySelector('[data-field=grams]').value;
    if (!quantity && !weight) return [];
    if (!quantity || !weight) throw new Error('Isi jumlah dan berat batch manual.');
    return [{batch_id: Number(row.dataset.id), version: Number(row.dataset.version),
      quantity, grams_per_unit: weight}];
  });
}
