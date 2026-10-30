(() => {
  const popup = document.querySelector('[data-auth-error-popup]');
  if (!popup || typeof popup.showModal !== 'function') return;

  popup.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const buttons = [...popup.querySelectorAll('button:not(:disabled)')]
      .filter(button => button.getClientRects().length);
    const first = buttons[0];
    const last = buttons[buttons.length - 1];
    if (first && ((event.shiftKey && document.activeElement === first)
      || (!event.shiftKey && document.activeElement === last))) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    }
  });

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
