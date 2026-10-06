const form = document.querySelector('#review-form');
if (form) {
  const output = document.querySelector('#review-error');
  async function submit(action) {
    const buttons = form.querySelectorAll('button'); buttons.forEach(b => b.disabled = true); output.textContent = '';
    try {
      const payload = {recipe_code: form.dataset.code, action,
        version: form.dataset.version ? Number(form.dataset.version) : null};
      if (action === 'save') { payload.rating = Number(form.elements.rating.value); payload.comment = form.elements.comment.value; }
      const response = await fetch(form.dataset.url, {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value}, body: JSON.stringify(payload)});
      let data; try { data = await response.json(); } catch { throw new Error('Sesi atau server bermasalah. Muat ulang halaman.'); }
      if (!response.ok) throw new Error(data.error || 'Ulasan gagal disimpan.');
      location.reload();
    } catch (error) { output.textContent = error.message; buttons.forEach(b => b.disabled = false); }
  }
  form.addEventListener('submit', event => { event.preventDefault(); submit('save'); });
  document.querySelector('#delete-review')?.addEventListener('click', () => {
    if (window.confirm('Hapus ulasan ini?')) submit('delete');
  });
}
