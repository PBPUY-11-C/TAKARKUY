(() => {
  const picker = document.querySelector('[data-avatar-picker]');
  if (!picker) return;
  const form = picker.closest('form');
  const image = picker.querySelector('[data-avatar-preview-image]');
  const initial = picker.querySelector('[data-avatar-preview-initial]');
  function update() {
    const selected = picker.querySelector('[name="avatar"]:checked');
    if (!selected) return;
    const source = selected.closest('[data-avatar-source]').dataset.avatarSource;
    const name = form.querySelector('[name="full_name"]').value.trim()
      || form.querySelector('[name="username"]').value.trim();
    const letter = (Array.from(name)[0] || '?').toLocaleUpperCase('id-ID');
    initial.textContent = letter;
    picker.querySelector('[data-avatar-choice-initial]').textContent = letter;
    image.hidden = !source;
    initial.hidden = Boolean(source);
    if (source) image.src = source;
    else image.removeAttribute('src');
  }
  picker.addEventListener('change', update);
  form.querySelector('[name="full_name"]').addEventListener('input', update);
  form.querySelector('[name="username"]').addEventListener('input', update);
  window.addEventListener('pageshow', update);
  update();
})();
