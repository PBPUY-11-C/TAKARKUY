// Modal panduan foto struk: dibuka hanya lewat tombol panduan, tidak otomatis.
(() => {
  const dialog = document.getElementById("receipt-guide-dialog");
  const opener = document.getElementById("receipt-guide-open");
  if (!dialog || !opener || typeof dialog.showModal !== "function") return;

  opener.addEventListener("click", () => {
    if (!dialog.open) dialog.showModal();
    opener.setAttribute("aria-expanded", "true");
  });

  dialog.querySelectorAll("[data-guide-close]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });

  let pressedOnBackdrop = false;
  dialog.addEventListener("mousedown", (event) => { pressedOnBackdrop = event.target === dialog; });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog && pressedOnBackdrop) dialog.close();
    pressedOnBackdrop = false;
  });

  dialog.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const focusable = [...dialog.querySelectorAll('button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')];
    if (!focusable.length) { event.preventDefault(); return; }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });

  dialog.addEventListener("close", () => {
    opener.setAttribute("aria-expanded", "false");
    opener.focus();
  });
})();
