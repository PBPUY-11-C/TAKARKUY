(() => {
  const popup = document.querySelector('[data-unsaved-popup]');
  const forms = [...document.querySelectorAll('.settings-panel form')];
  if (!popup || !forms.length) return;

  const snapshot = () => JSON.stringify(forms.map(form => [...new FormData(form)]
    .filter(([name]) => !['csrfmiddlewaretoken', 'version', 'action'].includes(name))));
  const original = snapshot();
  const dirty = () => popup.dataset.initialDirty === 'true' || snapshot() !== original;
  let leaving = false;
  let pending;
  function confirmLeave(action) {
    if (typeof popup.showModal !== 'function') {
      if (window.confirm('Perubahan belum disimpan. Tinggalkan?')) {
        leaving = true;
        action();
      }
      return;
    }
    pending = action;
    if (!popup.open) popup.showModal();
  }
  popup.querySelector('[data-unsaved-stay]').addEventListener('click', () => popup.close());
  popup.querySelector('[data-unsaved-leave]').addEventListener('click', () => {
    const action = pending;
    leaving = true;
    popup.close();
    action?.();
  });
  popup.addEventListener('close', () => { pending = undefined; });

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey
      || event.shiftKey || event.altKey || leaving || !dirty()) return;
    const link = event.target.closest('a[href]');
    if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    const url = new URL(link.href, window.location.href);
    if (!['http:', 'https:'].includes(url.protocol)) return;
    const samePage = url.origin === location.origin && url.pathname === location.pathname
      && url.search === location.search;
    if (samePage && (url.hash || link.getAttribute('href').startsWith('#'))) return;
    event.preventDefault();
    confirmLeave(() => window.location.assign(url.href));
  });

  // Intercept logout before the shared busy-button handler disables its button.
  document.addEventListener('submit', event => {
    if (forms.includes(event.target) || leaving || !dirty()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const form = event.target;
    const submitter = event.submitter;
    confirmLeave(() => submitter ? form.requestSubmit(submitter) : form.requestSubmit());
  }, true);
  document.addEventListener('submit', event => {
    // Runs after form validation handlers: an invalid submission stays guarded.
    if (forms.includes(event.target) && !event.defaultPrevented) leaving = true;
  });
  window.addEventListener('beforeunload', event => {
    if (leaving || !dirty()) return;
    event.preventDefault();
    event.returnValue = '';
  });
  window.addEventListener('pageshow', () => { leaving = false; });
})();
