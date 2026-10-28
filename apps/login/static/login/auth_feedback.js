(() => {
  const popup = document.querySelector('[data-auth-error-popup]');
  if (!popup || typeof popup.showModal !== 'function') return;

  popup.querySelectorAll('[data-close-auth-error]').forEach(button => {
    button.addEventListener('click', () => popup.close());
  });
  popup.addEventListener('close', () => {
    const field = document.querySelector('.auth-card form [aria-invalid="true"]')
      || document.querySelector('.auth-card input[name="username"]');
    if (field) {
      field.focus();
      field.scrollIntoView({ block: 'center', behavior: 'auto' });
    }
  });
  popup.showModal();
})();
