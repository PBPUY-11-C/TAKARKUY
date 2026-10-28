(() => {
  const configs = [
    { selector: '.recipe-photo-image', placeholder: 'recipe-photo-placeholder', label: image => image.alt },
    { selector: '.recipe-card-photo', placeholder: 'recipe-card-photo-placeholder', label: image => image.alt || image.closest('.recipe-card')?.querySelector('h3')?.textContent },
    { selector: '.meal-photo', placeholder: 'meal-photo-placeholder', label: image => image.alt },
  ];

  function replaceWithPlaceholder(image, className, label) {
    if (image.dataset.fallbackApplied === 'true') return;
    image.dataset.fallbackApplied = 'true';
    const placeholder = document.createElement('div');
    placeholder.className = className;
    placeholder.setAttribute('role', 'img');
    placeholder.setAttribute('aria-label', `${label || 'Foto resep'} tidak dapat dimuat`);
    const icon = document.createElement('span');
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '♨';
    placeholder.append(icon);
    if (className !== 'meal-photo-placeholder') {
      const message = document.createElement(className === 'recipe-photo-placeholder' ? 'span' : 'small');
      message.textContent = 'Foto tidak dapat dimuat';
      placeholder.append(message);
    }
    image.replaceWith(placeholder);
  }

  for (const config of configs) {
    for (const image of document.querySelectorAll(config.selector)) {
      image.addEventListener('error', () => replaceWithPlaceholder(image, config.placeholder, config.label(image)), { once: true });
      // A lazy image may have failed before this deferred script ran.
      if (image.complete && image.naturalWidth === 0) replaceWithPlaceholder(image, config.placeholder, config.label(image));
    }
  }
})();
