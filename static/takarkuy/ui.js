(() => {
  let stack;
  function toast(message, tone = "success") {
    if (!message) return;
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      stack.setAttribute("aria-hidden", "true"); // the page's own live region announces the text
      document.body.append(stack);
    }
    const item = document.createElement("div");
    item.className = `toast ${tone}`;
    const text = document.createElement("p");
    text.textContent = message;
    const close = document.createElement("button");
    close.type = "button";
    close.tabIndex = -1;
    close.textContent = "×";
    close.addEventListener("click", () => item.remove());
    item.append(text, close);
    stack.append(item);
    while (stack.children.length > 3) stack.firstElementChild.remove();
    setTimeout(() => item.remove(), tone === "error" ? 8000 : 4500);
  }

  function flash(message, tone = "success") {
    try { sessionStorage.setItem("takarkuy-flash", JSON.stringify({ message, tone })); } catch {  }
  }

  window.TakarKuy = { toast, flash };

  document.addEventListener("submit", (event) => {
    const form = event.target;
    const confirmText = form.dataset.confirm;
    if (confirmText && !window.confirm(confirmText)) {
      event.preventDefault();
      return;
    }
    if (event.defaultPrevented) return;
    const button = event.submitter || form.querySelector('[type="submit"]');
    if (!button || button.dataset.noBusy !== undefined) return;
    setTimeout(() => {
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
    });
  });

  window.addEventListener("pageshow", () => {
    document.querySelectorAll('[aria-busy="true"]').forEach((button) => {
      button.removeAttribute("aria-busy");
      button.disabled = false;
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target;
    if (target.closest("input, textarea, select, [contenteditable]")) return;
    const search = document.querySelector("[data-search-shortcut]");
    if (!search) return;
    event.preventDefault();
    search.focus();
    search.select();
  });

  document.addEventListener("DOMContentLoaded", () => {
    try {
      const saved = JSON.parse(sessionStorage.getItem("takarkuy-flash") || "null");
      sessionStorage.removeItem("takarkuy-flash");
      if (saved) toast(saved.message, saved.tone);
    } catch {  }
    document.querySelectorAll("[data-flash]").forEach((element) => toast(element.textContent.trim(), element.dataset.flash));
  });
})();
