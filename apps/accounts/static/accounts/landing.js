(() => {
  const form = document.getElementById('budget-calculator');
  if (!form) return;
  const output = document.getElementById('budget-result');
  const rupiah = new Intl.NumberFormat('id-ID', {
    style: 'currency', currency: 'IDR', maximumFractionDigits: 0,
  });
  function calculate(event) {
    if (event) event.preventDefault();
    if (!form.checkValidity()) {
      output.textContent = 'Isi budget, jumlah hari (1–7), dan jumlah orang (1–10) dengan angka bulat yang valid.';
      return;
    }
    const budget = Number(form.elements.budget.value);
    const days = Number(form.elements.days.value);
    const servings = Number(form.elements.servings.value);
    const daily = budget / days / servings;
    output.textContent = `${rupiah.format(daily)} per orang per hari, sekitar ${rupiah.format(daily / 3)} per waktu makan.`;
  }
  form.addEventListener('submit', calculate);
  form.addEventListener('input', calculate);
  calculate();
})();
