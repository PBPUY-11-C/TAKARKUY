(() => {
  const form = document.querySelector('[data-food-preferences]');
  if (!form) return;
  const servings = form.querySelector('[name="servings"]');
  const picker = form.querySelector('[data-ingredient-picker]');
  const search = picker.querySelector('#ingredient-search');
  const count = picker.querySelector('#ingredient-count');
  const ingredients = [...picker.querySelectorAll('input[type="checkbox"]')];
  const limit = Number(picker.dataset.limit);
  const checked = name => [...form.querySelectorAll(`input[name="${name}"]:checked`)];
  const label = input => (input.closest('label').querySelector('strong') || input.closest('label')).textContent.trim();
  const snapshot = () => JSON.stringify([...form.querySelectorAll('input[name]')]
    .filter(input => !['csrfmiddlewaretoken', 'version'].includes(input.name))
    .map(input => [input.name, input.type === 'checkbox' ? input.checked : input.value]));
  const original = snapshot();

  function updatePicker() {
    const selected = ingredients.filter(input => input.checked);
    const query = search.value.trim().toLocaleLowerCase('id-ID');
    let shown = 0;
    let alreadySelected = false;
    ingredients.forEach(input => {
      const matches = label(input).toLocaleLowerCase('id-ID').includes(query);
      if (matches && input.checked) alreadySelected = true;
      const visible = !input.checked && matches && (query || shown < 8);
      input.closest('label').parentElement.hidden = !visible;
      if (visible) shown += 1;
      input.disabled = !input.checked && selected.length >= limit;
    });
    count.textContent = `${selected.length}/${limit} dipilih`;
    const chosen = picker.querySelector('[data-selected-ingredients]');
    chosen.replaceChildren();
    selected.forEach(input => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `${label(input)} ${String.fromCharCode(215)}`;
      button.setAttribute('aria-label', `Hapus ${label(input)}`);
      button.addEventListener('click', () => {
        input.checked = false;
        update();
        search.focus();
      });
      chosen.append(button);
    });
    const empty = picker.querySelector('.ingredient-empty');
    empty.hidden = shown > 0;
    empty.textContent = alreadySelected && query ? 'Bahan ini sudah dipilih.' : 'Bahan tidak ditemukan. Coba nama lain.';
  }

  function update() {
    updatePicker();
    form.querySelector('[data-servings-change="-1"]').disabled = Number(servings.value) <= 1;
    form.querySelector('[data-servings-change="1"]').disabled = Number(servings.value) >= 10;
    form.querySelector('[data-pref-save-status]').textContent = snapshot() === original
      ? 'Simpan setelah selesai mengubah pilihan.' : 'Perubahan belum disimpan.';
  }
  function clearNotice(input) {
    const notice = input.closest('.pref-block')?.querySelector('[data-pref-notice]');
    if (notice) notice.hidden = true;
  }
  picker.querySelector('.ingredient-tools').hidden = false;
  form.querySelectorAll('[data-servings-change], [data-pref-clear]').forEach(button => { button.hidden = false; });
  form.noValidate = true;
  form.querySelectorAll('[data-servings-change]').forEach(button => button.addEventListener('click', () => {
    servings.value = Math.max(1, Math.min(10, (Number(servings.value) || 1) + Number(button.dataset.servingsChange)));
    clearNotice(servings);
    update();
  }));
  form.querySelector('[data-pref-clear]').addEventListener('click', () => {
    checked('allergens').forEach(input => { input.checked = false; });
    update();
  });
  form.addEventListener('change', event => {
    if (event.target === search) return;
    if (event.target.name === 'targets' && event.target.checked) {
      checked('targets').forEach(input => {
        if (input !== event.target && (input.value === 'seimbang' || event.target.value === 'seimbang')) input.checked = false;
      });
    }
    clearNotice(event.target);
    update();
  });
  form.addEventListener('input', event => { clearNotice(event.target); update(); });
  form.addEventListener('submit', event => {
    const invalid = [];
    if (!checked('targets').length) invalid.push(['target', 'Pilih minimal satu target makan.']);
    else if (checked('targets').length > 1 && checked('targets').some(input => input.value === 'seimbang')) invalid.push(['target', 'Seimbang tidak dapat digabung dengan target lain.']);
    if (!checked('meal_types').length) invalid.push(['schedule', 'Pilih minimal satu waktu makan.']);
    else if (!servings.checkValidity()) invalid.push(['schedule', 'Isi jumlah orang dengan angka bulat dari 1 sampai 10.']);
    if (ingredients.filter(input => input.checked).length > limit) invalid.push(['ingredients', 'Pilih maksimal 10 bahan.']);
    if (!invalid.length) return;
    event.preventDefault();
    invalid.forEach(([section, message]) => {
      const notice = form.querySelector(`[data-pref-notice="${section}"]`);
      notice.textContent = message;
      notice.hidden = false;
    });
    const section = form.querySelector(`#pref-${invalid[0][0]}`);
    section.querySelector('input:not([type="hidden"])').focus({ preventScroll: true });
    section.scrollIntoView({ block: 'center' });
  });
  update();
  window.addEventListener('pageshow', update);
})();
