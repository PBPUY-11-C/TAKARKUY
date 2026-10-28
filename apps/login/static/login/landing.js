(() => {
  const form = document.getElementById('budget-calculator');
  if (!form) return;
  const $ = (id) => document.getElementById(id);
  const rupiah = (n) => 'Rp' + Math.round(n).toLocaleString('id-ID');
  const budget = $('trial-budget');
  const range = $('trial-range');
  const days = $('trial-days');
  const servings = $('trial-servings');
  const menuData = JSON.parse($('landing-menu').textContent || '{}');
  const SLOTS = { sarapan: 'PAGI', makan_siang: 'SIANG', makan_malam: 'MALAM' };
  let freq = 3;
  let tick = 0;
  let meal = 0;

  const pop = (el, name = 'pop') => {
    el.classList.remove(name);
    void el.offsetWidth;
    el.classList.add(name);
  };
  const valid = (input) => input.value !== '' && input.checkValidity();
  const amount = () => Number(budget.value.replace(/\D/g, ''));
  const showAmount = (value) => {
    const digits = String(value).replace(/\D/g, '').replace(/^0+(?=\d)/, '');
    budget.value = digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  };
  const budgetValid = () => amount() >= Number(budget.dataset.min) && amount() <= Number(budget.dataset.max);

  function renderMenu() {
    const list = $('menu-list');
    const meals = freq === 2 ? ['makan_siang', 'makan_malam'] : ['sarapan', 'makan_siang', 'makan_malam'];
    let total = 0;
    const rows = meals.flatMap((key, i) => {
      const all = menuData[key] || [];
      if (!all.length) return [];
      const fit = all.filter(([cost]) => cost <= meal);
      const pool = fit.length ? fit.slice(-6) : all.slice(0, 1);
      const [cost, name] = pool[(tick + i * 2) % pool.length];
      total += cost;
      return [{ slot: SLOTS[key], name, cost }];
    });
    list.replaceChildren(...rows.map((row) => {
      const li = document.createElement('li');
      li.className = 'swap';
      const text = document.createElement('span');
      const slot = document.createElement('span');
      slot.className = 'menu-slot';
      slot.textContent = row.slot;
      const name = document.createElement('span');
      name.className = 'menu-name';
      name.textContent = row.name;
      text.append(slot, name);
      const price = document.createElement('span');
      price.className = 'menu-price';
      price.textContent = rupiah(row.cost);
      li.append(text, price);
      return li;
    }));
    $('menu-total').hidden = !rows.length || !meal;
    $('menu-sum').textContent = rupiah(total);
  }

  function calculate() {
    const ok = budgetValid() && valid(days) && valid(servings);
    $('budget-error').hidden = ok;
    if (!ok) {
      meal = 0;
      $('per-day').textContent = '—';
      $('per-meal').textContent = '—';
      renderMenu();
      return;
    }
    const daily = amount() / Number(days.value) / Number(servings.value);
    meal = daily / freq;
    $('per-day').textContent = rupiah(daily);
    $('per-meal').textContent = rupiah(meal);
    $('menu-of').textContent = rupiah(daily);
    $('portions').textContent = `${Number(days.value) * Number(servings.value) * freq} porsi total`;
    $('tier').textContent = meal < 5000 ? 'Hemat' : meal < 10000 ? 'Seimbang' : 'Leluasa';
    pop($('per-day'));
    pop($('per-meal'));
    form.querySelectorAll('[data-budget]').forEach((chip) => {
      chip.setAttribute('aria-pressed', String(Number(chip.dataset.budget) === amount()));
    });
    renderMenu();
  }

  budget.addEventListener('input', () => { showAmount(budget.value); range.value = amount(); calculate(); });
  range.addEventListener('input', () => { showAmount(range.value); calculate(); });
  days.addEventListener('input', calculate);
  servings.addEventListener('input', calculate);
  form.querySelectorAll('[data-budget]').forEach((chip) => chip.addEventListener('click', () => {
    range.value = chip.dataset.budget;
    showAmount(chip.dataset.budget);
    calculate();
  }));
  form.querySelectorAll('[data-step]').forEach((button) => button.addEventListener('click', () => {
    const input = $(button.dataset.step);
    const next = (Number(input.value) || 0) + Number(button.dataset.delta);
    input.value = Math.min(Number(input.max), Math.max(Number(input.min), next));
    calculate();
  }));
  form.querySelectorAll('[data-freq]').forEach((button) => button.addEventListener('click', () => {
    freq = Number(button.dataset.freq);
    form.querySelectorAll('[data-freq]').forEach((other) => other.setAttribute('aria-pressed', String(other === button)));
    const meals = freq === 2 ? ['makan_siang', 'makan_malam'] : ['sarapan', 'makan_siang', 'makan_malam'];
    $('meal-types').replaceChildren(...meals.map((value) => Object.assign(document.createElement('input'), { type: 'hidden', name: 'meal_types', value })));
    calculate();
  }));

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    calculate();
    if (!$('budget-error').hidden) return;
    const button = $('search-btn');
    button.setAttribute('aria-busy', 'true');
    button.textContent = 'Menyusun menu…';
    setTimeout(() => form.submit(), 600);
  });

  const cook = $('cook-btn');
  cook.addEventListener('click', () => {
    const cooked = cook.getAttribute('aria-pressed') !== 'true';
    cook.setAttribute('aria-pressed', String(cooked));
    cook.querySelector('span').textContent = cooked ? 'Sudah masak' : 'Masak sekarang';
    $('bayam-row').classList.toggle('used', cooked);
    const badge = $('bayam-badge');
    badge.textContent = cooked ? 'Habis' : 'Segera masak';
    badge.className = cooked ? 'badge badge-gone' : 'badge badge-soon pulse';
    $('egg-count').textContent = cooked ? '4' : '6';
    pop($('egg-count'));
  });

  const steps = document.querySelectorAll('.tool-steps li');
  steps.forEach((step) => step.addEventListener('pointerenter', () => {
    steps.forEach((other) => other.classList.toggle('on', other === step));
  }));

  calculate();
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
    setInterval(() => { tick += 1; renderMenu(); }, 5000);
  }
})();
