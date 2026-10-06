import { cookingPayload, manualValues } from './cooking.mjs';

const detail = document.querySelector('#recipe-detail');
const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
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
  let approved = null;
  let operationKey = null;
  let sequence = 0;
  let sending = false;
  function invalidate() {
    sequence += 1; approved = null; operationKey = null; confirm.disabled = true;
  }
  form.addEventListener('input', invalidate);
  document.querySelector('#open-cooking').addEventListener('click', () => dialog.showModal());
  document.querySelector('#close-cooking').addEventListener('click', () => { if (!sending) dialog.close(); });
  dialog.addEventListener('cancel', (event) => { if (sending) event.preventDefault(); });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    invalidate();
    const current = sequence;
    const check = form.querySelector('[type=submit]');
    check.disabled = true; errorText.textContent = '';
    try {
      const payload = cookingPayload(detail.dataset, form.elements, manualValues(manualBox));
      const data = await post(detail.dataset.previewUrl, payload);
      if (current !== sequence) return;
      output.replaceChildren();
      const heading = document.createElement('p');
      heading.textContent = data.complete ? 'Stok cukup. Pemakaian yang akan dicatat:' : 'Stok belum cukup:';
      output.append(heading);
      const names = new Map(data.ingredients.map(row => [row.ingredient_code, row.name]));
      for (const row of data.missing) {
        const line = document.createElement('p'); line.className = 'missing';
        line.textContent = `${names.get(row.ingredient_code)}: kurang ${Number(row.grams).toFixed(1)} g`;
        output.append(line);
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
    // Retain the same key after network errors: retry must not consume stock twice.
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
}
