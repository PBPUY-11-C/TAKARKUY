import {roundedAmount, scaleServings} from './servings.mjs';

const detail = document.querySelector('#recipe-detail');
const input = document.querySelector('#recipe-servings');
if (detail && input) {
  const baseServings = Number(detail.dataset.servings);
  const form = document.querySelector('#cooking-form');
  const summary = document.querySelector('#serving-summary');
  const status = document.querySelector('#serving-scale-status');
  const badge = detail.querySelector('.detail-heading .chip');
  const ingredientRows = [...detail.querySelectorAll('.ingredient-grid li')].map(row => ({
    amount: row.querySelector('span'),
    baseAmount: Number.parseFloat(row.querySelector('span').textContent),
    missing: row.querySelector('.missing'),
  }));
  const nutrition = [...detail.querySelectorAll('.metrics strong')].map(element => ({
    element,
    baseAmount: Number.parseFloat(element.textContent),
  }));
  const originalCost = summary.dataset.baseCost === '' ? null : Number(summary.dataset.baseCost);
  let quoteSequence = 0;

  input.addEventListener('input', () => {
    const servings = Number(input.value);
    if (!Number.isInteger(servings) || servings < 1 || servings > 10) {
      status.hidden = false;
      status.textContent = 'Masukkan jumlah porsi antara 1 dan 10.';
      return;
    }
    detail.dataset.servings = String(servings);
    if (form?.elements.servings) form.elements.servings.value = String(servings);
    for (const row of ingredientRows) {
      const amount = roundedAmount(scaleServings(row.baseAmount, baseServings, servings));
      if (amount !== null) row.amount.textContent = `${amount.toFixed(1)} g`;
      if (row.missing) row.missing.hidden = true;
    }
    for (const metric of nutrition) {
      const amount = roundedAmount(scaleServings(metric.baseAmount, baseServings, servings));
      if (amount !== null) metric.element.textContent = amount.toFixed(1);
    }
    if (summary && originalCost !== null && Number.isFinite(originalCost)) {
      const scaledCost = Math.round(scaleServings(originalCost, baseServings, servings));
      const formattedCost = new Intl.NumberFormat('id-ID', {maximumFractionDigits: 0}).format(scaledCost);
      summary.textContent = `${servings} porsi - Estimasi biaya proporsional Rp ${formattedCost} (harga referensi, bukan quote keranjang)`;
    } else if (summary) {
      summary.textContent = `${servings} porsi - Estimasi biaya belum tersedia`;
    }
    if (badge) badge.textContent = 'Periksa stok untuk porsi ini';
    status.hidden = false;
    status.textContent = 'Takaran dan gizi diperbarui. Periksa pemakaian stok sebelum mengonfirmasi masak.';
  });

  input.addEventListener('change', async () => {
    const servings = Number(input.value);
    if (!Number.isInteger(servings) || servings < 1 || servings > 10) return;
    const sequence = ++quoteSequence;
    status.hidden = false;
    status.textContent = 'Menghitung ulang estimasi harga dari katalog...';
    try {
      const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
      const response = await fetch(detail.dataset.estimateUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({recipe_code: detail.dataset.code, servings}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Estimasi harga gagal dihitung.');
      if (sequence !== quoteSequence || Number(input.value) !== servings) return;
      if (data.cost === null) {
        summary.textContent = `${servings} porsi - Estimasi harga belum tersedia di katalog`;
      } else {
        const amount = new Intl.NumberFormat('id-ID', {maximumFractionDigits: 0}).format(Number(data.cost));
        summary.textContent = `${servings} porsi - Estimasi belanja Rp ${amount} (harga referensi katalog, bukan belanja aktual)`;
      }
      status.textContent = 'Estimasi harga sudah dihitung ulang. Periksa pemakaian stok sebelum mengonfirmasi masak.';
    } catch (error) {
      if (sequence === quoteSequence) status.textContent = `${error.message} Estimasi proporsional tetap ditampilkan.`;
    }
  });
}
