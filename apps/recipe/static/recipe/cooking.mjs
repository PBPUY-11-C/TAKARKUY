// Menyusun payload pratinjau/masak; slot dan version rencana hanya disertakan bila ada slot.
export function cookingPayload(dataset, fields, manual, externalIngredients = []) {
  const payload = {recipe_code: dataset.code, servings: Number(fields.servings.value),
    allow_unknown_expiry: fields.allow_unknown_expiry.checked, manual};
  if (externalIngredients.length) payload.external_ingredients = externalIngredients;
  if (dataset.slot) { payload.planned_meal = Number(dataset.slot); payload.version = Number(dataset.version); }
  return payload;
}
// Mengambil isian batch manual; baris kosong dilewati, baris setengah terisi melempar Error.
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
