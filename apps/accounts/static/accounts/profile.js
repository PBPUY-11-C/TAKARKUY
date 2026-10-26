(() => {
  const picker = document.querySelector('[data-ingredient-picker]');
  if (!picker) return;
  const search = picker.querySelector('#ingredient-search');
  const count = picker.querySelector('#ingredient-count');
  const inputs = [...picker.querySelectorAll('input[type="checkbox"]')];
  const limit = Number(picker.dataset.limit);
  picker.querySelector('.ingredient-tools').hidden = false;

  function update() {
    const selected = inputs.filter(input => input.checked).length;
    const query = search.value.trim().toLocaleLowerCase('id-ID');
    let visible = 0;
    inputs.forEach(input => {
      const label = input.closest('label');
      const row = label.parentElement;
      // Keep selected ingredients visible so they can always be deselected.
      row.hidden = !input.checked && !label.textContent.toLocaleLowerCase('id-ID').includes(query);
      if (!row.hidden) visible += 1;
      input.disabled = !input.checked && selected >= limit;
    });
    count.textContent = `${selected}/${limit} dipilih`;
    picker.querySelector('.ingredient-empty').hidden = visible > 0;
  }
  search.addEventListener('input', update);
  inputs.forEach(input => input.addEventListener('change', update));
  window.addEventListener('pageshow', update);
  update();
})();
