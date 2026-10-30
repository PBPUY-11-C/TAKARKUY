import { csrfToken } from "./dom.mjs";
import { visit } from "./navigation.mjs";

// Move the ticked shopping-list items into Pantry after the user has bought them.
export function initPantryPurchases() {
  const button = document.getElementById("add-to-pantry");
  if (!button) return;
  const feedback = document.getElementById("plan-feedback");
  button.addEventListener("click", async () => {
    const items = Array.from(document.querySelectorAll(".pantry-pick:checked")).map((box) => ({
      ingredient_code: box.dataset.ingredient,
      grams: Number(box.dataset.grams),
    }));
    if (!items.length) {
      feedback.textContent = "Centang minimal satu bahan yang sudah dibeli.";
      globalThis.TakarKuy?.toast(feedback.textContent, "error");
      return;
    }
    button.disabled = true;
    feedback.textContent = "Memasukkan belanjaan ke Pantry…";
    try {
      const response = await fetch(button.dataset.url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ version: Number(button.dataset.version), items }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `Request belum berhasil (kode ${response.status}).`);
      button.closest("dialog")?.close();
      await visit(window.location.href, `${body.saved} bahan masuk ke Pantry. Atur lokasi/tanggal di Pantry bila perlu.`);
    } catch (error) {
      feedback.textContent = error.message;
      globalThis.TakarKuy?.toast(error.message, "error");
      button.disabled = false;
    }
  });
}
