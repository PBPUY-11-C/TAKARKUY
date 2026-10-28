const reportForm = document.querySelector('#recipe-data-report');

if (reportForm) {
  const status = document.querySelector('#recipe-data-report-status');
  const submit = reportForm.querySelector('[type="submit"]');
  const csrf = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;

  reportForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!reportForm.reportValidity()) return;
    submit.disabled = true;
    status.textContent = 'Mengirim laporan…';
    const formData = new FormData(reportForm);
    try {
      const response = await fetch(reportForm.dataset.url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf || ''},
        body: JSON.stringify({
          recipe_code: reportForm.dataset.code,
          category: formData.get('category'),
          details: formData.get('details'),
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Laporan tidak dapat dikirim. Coba lagi.');
      reportForm.reset();
      status.textContent = 'Terima kasih. Laporan terkirim untuk ditinjau tim.';
    } catch (error) {
      status.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
}
