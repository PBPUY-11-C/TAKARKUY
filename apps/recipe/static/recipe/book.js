import { cookingPayload, manualValues } from './cooking.mjs';

const detail = document.querySelector('#recipe-detail');
const csrf = document.querySelector('#csrf-bootstrap [name=csrfmiddlewaretoken]')?.value
  || document.querySelector('[name=csrfmiddlewaretoken]')?.value
  || '';
const message = document.querySelector('#page-message');
async function post(url, payload) {
  const response = await fetch(url, {method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify(payload)});
  const data = await response.json().catch(() => ({error: 'Respons server tidak dapat dibaca. Muat ulang.'}));
  if (!response.ok) throw new Error(data.error || 'Permintaan gagal.');
  return data;
}
function showError(error) { message.textContent = error.message; message.hidden = false; }
for (const button of document.querySelectorAll('[data-remove-favorite]')) {
  button.addEventListener('click', async () => {
    button.disabled = true;
    try { await post(button.dataset.url, {recipe_code: button.dataset.removeFavorite, favorite: false}); location.reload(); }
    catch (error) { showError(error); button.disabled = false; }
  });
}
if (detail) {
  const favorite = document.querySelector('#favorite-button');
  favorite.addEventListener('click', async () => {
    favorite.disabled = true;
    try {
      await post(detail.dataset.favoriteUrl, {recipe_code: detail.dataset.code,
        favorite: favorite.getAttribute('aria-pressed') !== 'true'});
      location.reload();
    } catch (error) { showError(error); favorite.disabled = false; }
  });
  const dialog = document.querySelector('#cooking-dialog');
  const form = document.querySelector('#cooking-form');
  const output = document.querySelector('#cooking-preview');
  const errorText = document.querySelector('#cooking-error');
  const manualBox = document.querySelector('#manual-batches');
  const confirm = document.querySelector('#confirm-cooking');
  const openCooking = document.querySelector('#open-cooking');
  let dialogTrigger = null;
  let approved = null;
  let operationKey = null;
  let sequence = 0;
  let sending = false;
  const externalIngredients = new Map();
  function invalidate(event) {
    sequence += 1; approved = null; operationKey = null; confirm.disabled = true;
    if (event?.target?.matches?.('[data-external-ingredient]')) {
      const {ingredientCode, grams} = event.target.dataset;
      if (event.target.checked) externalIngredients.set(ingredientCode, grams);
      else externalIngredients.delete(ingredientCode);
    } else if (event) {
      externalIngredients.clear();
      document.querySelectorAll('#cooking-preview [data-external-ingredient]').forEach((input) => {
        input.checked = false;
      });
    }
  }
  form.addEventListener('input', invalidate);
  openCooking.addEventListener('click', () => {
    dialogTrigger = openCooking;
    dialog.showModal();
    form.elements.namedItem('servings')?.focus();
  });
  document.querySelector('#close-cooking').addEventListener('click', () => { if (!sending) dialog.close(); });
  dialog.addEventListener('cancel', (event) => { if (sending) event.preventDefault(); });
  dialog.addEventListener('close', () => {
    if (dialogTrigger?.isConnected && !dialogTrigger.disabled) dialogTrigger.focus();
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    invalidate();
    const current = sequence;
    const check = form.querySelector('[type=submit]');
    check.disabled = true; errorText.textContent = '';
    try {
      const externalValues = [...externalIngredients].map(([ingredient_code, grams]) => ({
        ingredient_code, grams,
      }));
      const payload = cookingPayload(
        detail.dataset, form.elements, manualValues(manualBox), externalValues,
      );
      const data = await post(detail.dataset.previewUrl, payload);
      if (current !== sequence) return;
      output.replaceChildren();
      externalIngredients.clear();
      for (const item of data.external_ingredients || []) {
        externalIngredients.set(item.ingredient_code, item.grams);
        const label = document.createElement('label'); label.className = 'check-field external-ingredient';
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
        checkbox.checked = true;
        checkbox.dataset.externalIngredient = 'true';
        checkbox.dataset.ingredientCode = item.ingredient_code;
        checkbox.dataset.grams = item.grams;
        const text = document.createElement('span');
        text.textContent = `${item.name}: ${Number(item.grams).toFixed(1)} g tersedia di luar Pantry (stok Pantry tidak dikurangi untuk bagian ini).`;
        label.append(checkbox, text); output.append(label);
      }
      const heading = document.createElement('p');
      heading.textContent = data.complete
        ? (data.external_ingredients?.length
          ? 'Semua bahan tercukupi. Pemakaian stok Pantry yang akan dicatat:'
          : 'Stok cukup. Pemakaian yang akan dicatat:')
        : 'Stok belum cukup:';
      output.append(heading);
      const names = new Map(data.ingredients.map(row => [row.ingredient_code, row.name]));
      for (const row of data.missing) {
        const line = document.createElement('p'); line.className = 'missing';
        line.textContent = `${names.get(row.ingredient_code)}: kurang ${Number(row.grams).toFixed(1)} g`;
        output.append(line);
        const label = document.createElement('label'); label.className = 'check-field external-ingredient';
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
        checkbox.dataset.externalIngredient = 'true';
        checkbox.dataset.ingredientCode = row.ingredient_code;
        checkbox.dataset.grams = row.grams;
        const text = document.createElement('span');
        text.textContent = `Saya punya kekurangan ${Number(row.grams).toFixed(1)} g ini di luar Pantry. Stok Pantry yang tersedia tetap akan dipakai. Centang lalu periksa ulang.`;
        label.append(checkbox, text); output.append(label);
      }
      for (const row of data.batches) {
        const line = document.createElement('p');
        line.textContent = `${row.name}: ${row.quantity} ${row.unit} (${Number(row.grams).toFixed(1)} g)${row.manual ? ' · manual' : ''}`;
        output.append(line);
      }
      for (const batch of data.manual_batches) {
        if ([...manualBox.children].some(row => row.dataset.id === String(batch.batch_id))) continue;
        const row = document.createElement('fieldset'); row.className = 'manual-row';
        row.dataset.id = batch.batch_id; row.dataset.version = batch.version;
        const title = document.createElement('legend');
        title.textContent = `${batch.name} · tersedia ${batch.quantity} ${batch.unit} · dipakai manual`;
        row.append(title);
        for (const [key, titleText] of [['quantity', `Jumlah (${batch.unit})`], ['grams', 'Berat per unit (g)']]) {
          const label = document.createElement('label'); label.textContent = titleText;
          const input = document.createElement('input'); input.type = 'number'; input.min = '0.000001';
          input.step = '0.000001'; input.dataset.field = key; label.append(input); row.append(label);
        }
        manualBox.append(row);
      }
      approved = data.complete ? payload : null;
      confirm.disabled = !approved;
    } catch (error) { errorText.textContent = error.message; }
    finally { check.disabled = false; }
  });
  confirm.addEventListener('click', async () => {
    if (!approved || sending) return;
    operationKey ||= crypto.randomUUID();
    sending = true; confirm.disabled = true; errorText.textContent = '';
    for (const input of form.querySelectorAll('input,button')) input.disabled = true;
    try {
      await post(detail.dataset.cookUrl, {...approved, operation_key: operationKey});
      location.reload();
    } catch (error) {
      errorText.textContent = error.message;
      for (const input of form.querySelectorAll('input,button')) input.disabled = false;
      confirm.disabled = !approved;
    } finally { sending = false; }
  });
  const slotStatus = document.querySelector('#slot-status');
  if (slotStatus) {
    slotStatus.addEventListener('click', async () => {
      slotStatus.disabled = true;
      try {
        await post(slotStatus.dataset.url, {planned_meal: Number(detail.dataset.slot),
          version: Number(detail.dataset.version), status: slotStatus.dataset.status});
        location.reload();
      } catch (error) { showError(error); slotStatus.disabled = false; }
    });
  }
}
