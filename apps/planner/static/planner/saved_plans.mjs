import { request } from "./api.mjs";
import { visit } from "./navigation.mjs";

function changeSavedCount(delta) {
  document.querySelectorAll("[data-saved-count]").forEach((counter) => {
    counter.textContent = String(Math.max(0, Number(counter.textContent) + delta));
  });
}

function emptySavedRow() {
  const row = document.createElement("li");
  row.className = "muted";
  row.textContent = "Belum ada rencana tersimpan. Buat rencana, lalu tekan Simpan Rencana.";
  return row;
}

// Save a draft to "Rencana Saya", and delete saved plans optimistically with rollback on failure.
export function initSavedPlans() {
  const feedback = document.getElementById("plan-feedback");

  document.querySelectorAll("[data-save-plan]").forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const replaceOriginal = event.submitter?.name === "replace_original";
    if (replaceOriginal && !window.confirm("Ganti isi rencana asal dengan draft ini?")) return;
    const buttons = [...form.querySelectorAll('button[type="submit"]')];
    const status = form.querySelector(".status");
    const title = form.querySelector('[name="title"]');
    const error = form.querySelector("[data-save-error]");
    const before = status?.textContent;
    buttons.forEach((button) => { button.disabled = true; });
    if (status) status.textContent = "· Menyimpan…";
    title?.removeAttribute("aria-invalid");
    if (error) error.hidden = true;
    try {
      const values = new FormData(form);
      const data = await request(form.dataset.url, { version: Number(form.dataset.version),
        title: values.get("title"), starts_on: values.get("starts_on") || null, replace_original: replaceOriginal });
      await visit(data.url, "Rencana tersimpan.");
    } catch (failure) {
      if (status) status.textContent = before;
      if (error) { error.textContent = failure.message; error.hidden = false; }
      if (!title?.value.trim()) { title?.setAttribute("aria-invalid", "true"); title?.focus(); }
      globalThis.TakarKuy?.toast(failure.message, "error");
    }
    finally { buttons.forEach((button) => { button.disabled = false; }); }
  }));

  document.querySelectorAll("[data-delete-plan]").forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm(`Hapus rencana “${button.dataset.title}”? Stok pantry tidak berubah.`)) return;
    const row = button.closest("li");
    const list = row.parentElement;
    const next = row.nextSibling;
    const message = `Rencana “${button.dataset.title}” dihapus.`;
    row.remove();
    changeSavedCount(-1);
    try {
      const data = await request(button.dataset.url, { version: Number(button.dataset.version) });
      if (document.querySelector('.planner-form [name="plan_id"]')?.value === button.dataset.planId) {
        await visit(data.url, message);
        return;
      }
      if (!list.querySelector("[data-delete-plan]")) list.append(emptySavedRow());
      feedback.textContent = message;
      globalThis.TakarKuy?.toast(message);
    } catch (error) {
      list.insertBefore(row, next);
      changeSavedCount(1);
      feedback.textContent = error.message;
      globalThis.TakarKuy?.toast(error.message, "error");
    }
  }));
}
