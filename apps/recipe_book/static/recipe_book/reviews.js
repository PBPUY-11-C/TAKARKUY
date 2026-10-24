const form = document.querySelector('#review-form');
if (form) {
  const output = document.querySelector('#review-error');
  const photoInput = form.elements.namedItem('photo');
  const photoPermission = form.elements.namedItem('photo_permission');
  const photoPreview = document.querySelector('#review-photo-preview');
  let previewUrl = null;

  async function readResponse(response) {
    let data;
    try { data = await response.json(); }
    catch { throw new Error('Sesi atau server bermasalah. Muat ulang halaman.'); }
    if (!response.ok) throw new Error(data.error || 'Ulasan gagal disimpan.');
    return data;
  }

  async function submit(action) {
    const buttons = form.querySelectorAll('button');
    buttons.forEach(button => button.disabled = true);
    output.textContent = '';
    try {
      const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
      const payload = {
        recipe_code: form.dataset.code,
        action,
        version: form.dataset.version ? Number(form.dataset.version) : null,
      };
      if (action === 'save') {
        payload.rating = Number(form.elements.rating.value);
        payload.comment = form.elements.comment.value;
        if (photoInput.files.length && !photoPermission.checked) {
          throw new Error('Setujui izin penggunaan foto sebelum mengunggah.');
        }
      }
      const savedReview = await readResponse(await fetch(form.dataset.url, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify(payload),
      }));

      if (action === 'save') {
        form.dataset.version = String(savedReview.version);
        const photo = photoInput.files[0];
        if (photo) {
          const body = new FormData();
          body.append('recipe_code', form.dataset.code);
          body.append('version', form.dataset.version);
          body.append('photo', photo);
          body.append('photo_permission', photoPermission.checked ? 'on' : '');
          try {
            await readResponse(await fetch(form.dataset.photoUrl, {
              method: 'POST', credentials: 'same-origin',
              headers: {'X-CSRFToken': csrf}, body,
            }));
          } catch (error) {
            output.textContent = `Ulasan tersimpan, tetapi foto belum terunggah: ${error.message}`;
            buttons.forEach(button => button.disabled = false);
            return;
          }
        }
      }
      location.reload();
    } catch (error) {
      output.textContent = error.message;
      buttons.forEach(button => button.disabled = false);
    }
  }

  photoInput?.addEventListener('change', () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    const file = photoInput.files[0];
    if (!file) { photoPreview.hidden = true; return; }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 6 * 1024 * 1024) {
      photoInput.value = '';
      photoPreview.hidden = true;
      output.textContent = 'Pilih foto JPG, PNG, atau WebP maksimal 6 MB.';
      return;
    }
    output.textContent = '';
    previewUrl = URL.createObjectURL(file);
    photoPreview.src = previewUrl;
    photoPreview.hidden = false;
  });

  form.addEventListener('submit', event => { event.preventDefault(); submit('save'); });
  document.querySelector('#delete-review')?.addEventListener('click', () => {
    if (window.confirm('Hapus ulasan dan foto yang Anda bagikan?')) submit('delete');
  });
  window.addEventListener('pagehide', () => { if (previewUrl) URL.revokeObjectURL(previewUrl); });
}
