const form = document.querySelector('#recipe-note-form');
if (form) {
  const field = form.elements.namedItem('content');
  const status = document.querySelector('#recipe-note-status');
  const buttons = [...form.querySelectorAll('button')];

  async function save(content) {
    buttons.forEach(button => { button.disabled = true; });
    status.textContent = '';
    try {
      const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
      const response = await fetch(form.dataset.url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({recipe_code: form.dataset.code, content}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Catatan gagal disimpan.');
      field.value = content;
      status.textContent = data.saved ? 'Catatan pribadi tersimpan.' : 'Catatan pribadi dihapus.';
    } catch (error) {
      status.textContent = error.message || 'Catatan gagal disimpan.';
    } finally {
      buttons.forEach(button => { button.disabled = false; });
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    save(field.value);
  });
  document.querySelector('#clear-recipe-note')?.addEventListener('click', () => {
    if (!field.value.trim() || window.confirm('Hapus catatan pribadi untuk resep ini?')) save('');
  });
}
