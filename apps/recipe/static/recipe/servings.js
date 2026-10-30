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
    row,
    amount: row.querySelector('span'),
    baseAmount: Number.parseFloat(row.querySelector('span').textContent),
    missing: row.querySelector('.missing'),
    status: row.querySelector('.ingredient-status'),
  }));
  // Animasi kecil saat angka berubah (CSS: .is-updated, hanya bila gerakan tidak dikurangi).
  const flash = (element) => {
    if (!element) return;
    element.classList.remove('is-updated');
    void element.offsetWidth;
    element.classList.add('is-updated');
  };
  // Tombol − / + di sebelah input porsi: ubah nilai lalu kirim event yang sama seperti mengetik.
  for (const button of document.querySelectorAll('[data-serving-step]')) {
    button.addEventListener('click', () => {
      const before = Number(input.value);
      if (button.dataset.servingStep === '-1') input.stepDown(); else input.stepUp();
      if (Number(input.value) === before) return;
      input.dataset.dir = Number(input.value) > before ? 'up' : 'down';
      input.dispatchEvent(new Event('input', {bubbles: true}));
      input.dispatchEvent(new Event('change', {bubbles: true}));
      window.setTimeout(() => { delete input.dataset.dir; }, 400);
    });
  }
  const syncStepButtons = () => {
    const value = Number(input.value);
    for (const button of document.querySelectorAll('[data-serving-step]')) {
      const atLimit = button.dataset.servingStep === '-1' ? value <= Number(input.min) : value >= Number(input.max);
      button.setAttribute('aria-disabled', String(atLimit));
    }
  };
  syncStepButtons();
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
      if (amount !== null) { row.amount.textContent = `${amount.toFixed(1)} g`; flash(row.amount); }
      // Stock shortages depend on Pantry contents and are recalculated in the cooking preview.
      const stock = row.row.dataset.stock;
      if (row.status && (stock === 'ok' || stock === 'short' || stock === 'check')) {
        row.row.dataset.stock = 'check';
        row.status.classList.remove('missing');
        const marker = document.createElement('b');
        marker.setAttribute('aria-hidden', 'true');
        marker.textContent = '≈';
        row.status.replaceChildren(marker, ' Periksa stok untuk porsi ini');
      } else if (row.missing) row.missing.hidden = true;
      if (amount !== null) row.amount.textContent = `${amount.toFixed(1)} g`;
      if (row.missing) row.missing.hidden = true;
    }
    for (const metric of nutrition) {
      const amount = roundedAmount(scaleServings(metric.baseAmount, baseServings, servings));
      if (amount !== null) { metric.element.textContent = amount.toFixed(1); flash(metric.element); }
    }
    flash(summary);
    flash(input);
    syncStepButtons();
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
      flash(summary);
      status.textContent = 'Estimasi harga sudah dihitung ulang. Periksa pemakaian stok sebelum mengonfirmasi masak.';
    } catch (error) {
      if (sequence === quoteSequence) status.textContent = `${error.message} Estimasi proporsional tetap ditampilkan.`;
    }
  });
}
