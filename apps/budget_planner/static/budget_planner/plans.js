(() => {
  const feedback = document.getElementById("plan-feedback");
  const dialog = document.getElementById("plan-dialog");
  if (!dialog) return;
  const picker = document.getElementById("replacement-picker");
  const selector = document.getElementById("replacement-recipe");
  const resultPanel = document.getElementById("preview-result");
  const previewFeedback = document.getElementById("preview-feedback");
  const previewButton = document.getElementById("request-preview");
  const applyButton = document.getElementById("apply-preview");
  const budgetField = document.getElementById("new-budget");
  const rupiah = (value) => "Rp " + Number(value).toLocaleString("id-ID");
  let replacement = null;
  let proposal = null;
  let dialogGeneration = 0;
  dialog.addEventListener("close", () => { dialogGeneration += 1; proposal = null; });

  // A non-JSON reply is a page from Django itself (CSRF, login, crash), so the
  // status code is the only reliable hint of what went wrong.
  function failureMessage(status) {
    if (status === 403) return "Sesi keamanan halaman kedaluwarsa. Muat ulang halaman lalu coba lagi.";
    if (status === 401 || status === 302) return "Sesi login berakhir. Masuk lagi lalu coba kembali.";
    if (status === 404) return "Rencana tidak ditemukan atau sudah diganti. Muat ulang halaman.";
    if (status >= 500) return `Server sedang bermasalah (kode ${status}). Coba lagi sebentar lagi.`;
    return `Request belum berhasil (kode ${status}). Muat ulang halaman.`;
  }

  async function request(url, data) {
    const options = { credentials: "same-origin", headers: { Accept: "application/json" } };
    if (data !== undefined) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.headers["X-CSRFToken"] = document.querySelector('[name="csrfmiddlewaretoken"]').value;
      options.body = JSON.stringify(data);
    }
    const response = await fetch(url, options);
    let body;
    try { body = await response.json(); } catch { throw new Error(failureMessage(response.status)); }
    if (!response.ok) throw new Error(body.error || "Request belum berhasil.");
    return body;
  }

  function resetDialog() {
    dialogGeneration += 1;
    proposal = null;
    replacement = null;
    selector.disabled = false;
    previewButton.disabled = false;
    picker.hidden = true;
    resultPanel.hidden = true;
    previewFeedback.textContent = "";
    document.getElementById("preview-title").textContent = "Pratinjau Menu";
    if (!dialog.open) dialog.showModal();
  }

  function showProposal(data) {
    proposal = data;
    resultPanel.hidden = false;
    previewFeedback.textContent = "";
    const delta = Number(data.delta);
    document.getElementById("preview-cost").textContent =
      `Estimasi belanja ${rupiah(data.before)} → ${rupiah(data.after)}. ` +
      (delta > 0 ? `Naik ${rupiah(delta)}.` : delta < 0 ? `Turun ${rupiah(-delta)}.` : "Total tetap.");
    document.getElementById("preview-budget").textContent = data.over_budget > 0
      ? `Melebihi budget ${rupiah(data.budget)} sebesar ${rupiah(data.over_budget)}. Pilih menu lain, batalkan, atau setujui budget baru.`
      : `Masih dalam budget ${rupiah(data.budget)}. Sisa ${rupiah(data.budget - data.after)}.`;
    document.getElementById("preview-parameters").textContent = `${data.days} hari · ${data.servings} orang. Target gizi dan pantangan telah diperiksa.`;
    document.getElementById("preview-notes").textContent = (data.preference_notes || []).join(" ");
    document.getElementById("budget-increase").hidden = data.over_budget <= 0;
    budgetField.value = String(data.after);
    applyButton.textContent = data.over_budget > 0 ? "Naikkan Budget dan Terapkan ke Draft" : "Terapkan ke Draft";
    const schedule = document.getElementById("preview-schedule");
    schedule.replaceChildren();
    for (const day of data.schedule) {
      const row = document.createElement("p");
      row.textContent = `Hari ${day.number}: ` + day.meals.map((meal) => `${meal.label}: ${meal.name}`).join(" · ");
      if (data.nutrition_targets_set) row.textContent += ` (${day.protein} g protein · ${day.calories} kkal/orang)`;
      schedule.append(row);
    }
    const shopping = document.getElementById("preview-shopping");
    shopping.replaceChildren();
    for (const group of data.shopping_groups) {
      for (const item of group.items) {
        const row = document.createElement("li");
        row.textContent = `${item.name}: ${item.quantity} g · ${rupiah(item.cost)}` +
          (item.purchase_units ? ` · beli ${item.purchase_units} ${item.purchase_unit}` : "");
        shopping.append(row);
      }
    }
  }

  document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  document.querySelectorAll("[data-replace-menu]").forEach((button) => button.addEventListener("click", async () => {
    resetDialog();
    const generation = dialogGeneration;
    previewFeedback.textContent = "Mencari alternatif…";
    button.disabled = true;
    try {
      const url = new URL(button.dataset.alternativesUrl, window.location.origin);
      url.searchParams.set("day", button.dataset.day);
      url.searchParams.set("meal", button.dataset.meal);
      const data = await request(url);
      if (generation !== dialogGeneration || !dialog.open) return;
      if (data.version !== Number(button.dataset.version)) throw new Error("Rencana berubah di perangkat lain. Muat ulang halaman.");
      replacement = { url: button.dataset.previewUrl, version: Number(button.dataset.version),
        day: Number(button.dataset.day), meal: button.dataset.meal };
      selector.replaceChildren();
      for (const recipe of data.recipes) {
        const option = document.createElement("option");
        option.value = recipe.recipe_code;
        const delta = Number(recipe.delta) || 0;
        option.textContent = delta ? `${recipe.name} (${delta > 0 ? "+" : "−"}${rupiah(Math.abs(delta))})` : recipe.name;
        selector.append(option);
      }
      picker.hidden = false;
      previewButton.disabled = !data.recipes.length;
      previewFeedback.textContent = data.recipes.length ? "" : "Belum ada menu lain yang masih masuk budget dan target gizi hari ini. Menu lama tetap dipertahankan.";
    } catch (error) { if (generation === dialogGeneration) previewFeedback.textContent = error.message; }
    finally { button.disabled = false; }
  }));

  selector.addEventListener("change", () => { proposal = null; resultPanel.hidden = true; previewFeedback.textContent = ""; });
  previewButton.addEventListener("click", async () => {
    if (!replacement || !selector.value) return;
    const generation = dialogGeneration;
    proposal = null;
    resultPanel.hidden = true;
    previewFeedback.textContent = "Menghitung ulang seluruh belanja dan target gizi…";
    previewButton.disabled = true;
    selector.disabled = true;
    try {
      const data = await request(replacement.url, { action: "replace", version: replacement.version,
        day: replacement.day, meal: replacement.meal, recipe: selector.value });
      if (generation === dialogGeneration && dialog.open) showProposal(data);
    }
    catch (error) { if (generation === dialogGeneration) previewFeedback.textContent = error.message; }
    finally { if (generation === dialogGeneration) { previewButton.disabled = false; selector.disabled = false; } }
  });

  document.querySelectorAll("[data-regenerate]").forEach((button) => button.addEventListener("click", async () => {
    resetDialog();
    const generation = dialogGeneration;
    previewFeedback.textContent = "Mencari susunan menu lain…";
    button.disabled = true;
    try {
      const data = await request(button.dataset.previewUrl, { action: "regenerate", version: Number(button.dataset.version) });
      if (generation === dialogGeneration && dialog.open) showProposal(data);
    }
    catch (error) { if (generation === dialogGeneration) previewFeedback.textContent = error.message; }
    finally { button.disabled = false; }
  }));

  applyButton.addEventListener("click", async () => {
    if (!proposal) return;
    applyButton.disabled = true;
    try {
      const data = await request(proposal.apply_url, proposal.over_budget > 0
        ? { new_budget: budgetField.value } : {});
      window.location.assign(data.url);
    } catch (error) { previewFeedback.textContent = error.message; }
    finally { applyButton.disabled = false; }
  });

  document.querySelectorAll("[data-save-plan]").forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const replaceOriginal = event.submitter?.name === "replace_original";
    if (replaceOriginal && !window.confirm("Ganti isi rencana asal dengan draft ini?")) return;
    const buttons = [...form.querySelectorAll('button[type="submit"]')];
    buttons.forEach((button) => { button.disabled = true; });
    feedback.textContent = "Menyimpan rencana…";
    try {
      const values = new FormData(form);
      const data = await request(form.dataset.url, { version: Number(form.dataset.version),
        title: values.get("title"), starts_on: values.get("starts_on"), replace_original: replaceOriginal });
      window.location.assign(data.url);
    } catch (error) { feedback.textContent = error.message; feedback.scrollIntoView({ block: "center" }); }
    finally { buttons.forEach((button) => { button.disabled = false; }); }
  }));

  document.querySelectorAll("[data-delete-plan]").forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm(`Hapus rencana “${button.dataset.title}”? Stok pantry tidak berubah.`)) return;
    button.disabled = true;
    try { const data = await request(button.dataset.url, { version: Number(button.dataset.version) }); window.location.assign(data.url); }
    catch (error) { feedback.textContent = error.message; feedback.scrollIntoView({ block: "center" }); }
    finally { button.disabled = false; }
  }));

  const pending = document.getElementById("pending-plan-preview");
  if (pending) { resetDialog(); showProposal(JSON.parse(pending.textContent)); }
})();

// Move checked shopping-list items into the pantry once they were bought.
(() => {
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
          "X-CSRFToken": document.querySelector('[name="csrfmiddlewaretoken"]').value,
        },
        body: JSON.stringify({ version: Number(button.dataset.version), items }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `Request belum berhasil (kode ${response.status}).`);
      feedback.textContent = `${body.saved} bahan masuk ke Pantry. Atur lokasi/tanggal di Smart Pantry bila perlu.`;
      location.reload();
    } catch (error) {
      feedback.textContent = error.message;
      button.disabled = false;
    }
  });
})();
