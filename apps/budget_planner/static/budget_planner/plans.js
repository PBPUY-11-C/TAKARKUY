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
  const pickerTotal = document.getElementById("picker-total");
  const rupiah = (value) => "Rp " + Number(value).toLocaleString("id-ID");
  let replacement = null;
  let deltas = {};
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

  // Assigning a URL that differs only in its #fragment does not reload the page,
  // which would leave a deleted or renamed plan on screen.
  function navigate(url) {
    const destination = new URL(url, window.location.origin);
    if (destination.pathname === window.location.pathname && destination.search === window.location.search) {
      window.location.hash = destination.hash;
      window.location.reload();
    } else {
      window.location.assign(url);
    }
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

  function resetDialog(title = "Pratinjau menu", subtitle = "") {
    dialogGeneration += 1;
    proposal = null;
    replacement = null;
    deltas = {};
    selector.disabled = false;
    previewButton.disabled = false;
    previewButton.hidden = true;
    applyButton.hidden = true;
    picker.hidden = true;
    resultPanel.hidden = true;
    previewFeedback.textContent = "";
    pickerTotal.textContent = "";
    document.getElementById("preview-title").textContent = title;
    document.getElementById("preview-subtitle").textContent = subtitle;
    if (!dialog.open) dialog.showModal();
  }

  // The total after the chosen swap; alternatives already fit the budget.
  function showPickedTotal() {
    if (!replacement || !(selector.value in deltas)) return;
    pickerTotal.textContent = `Total belanja jadi ${rupiah(replacement.total + deltas[selector.value])} / ${rupiah(replacement.budget)}`;
  }

  function showProposal(data) {
    proposal = data;
    resultPanel.hidden = false;
    previewButton.hidden = true;
    applyButton.hidden = false;
    previewFeedback.textContent = "";
    const delta = Number(data.delta);
    document.getElementById("preview-cost").textContent =
      `Belanja ${rupiah(data.before)} → ${rupiah(data.after)} · ` +
      (delta > 0 ? `Naik ${rupiah(delta)}` : delta < 0 ? `Turun ${rupiah(-delta)}` : "Total tetap");
    document.getElementById("preview-budget").textContent = data.over_budget > 0
      ? `Melebihi budget ${rupiah(data.budget)} sebesar ${rupiah(data.over_budget)}.`
      : `Masih dalam budget ${rupiah(data.budget)} · sisa ${rupiah(data.budget - data.after)}`;
    document.getElementById("preview-parameters").textContent = `${data.days} hari · ${data.servings} orang`;
    document.getElementById("preview-notes").textContent = (data.preference_notes || []).join(" ");
    document.getElementById("budget-increase").hidden = data.over_budget <= 0;
    budgetField.value = String(data.after);
    applyButton.textContent = data.over_budget > 0 ? "Naikkan budget & pakai" : "Pakai menu ini";
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

  // Each close button closes its own dialog (Rencana Saya, Pantry, or the preview).
  document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => (button.closest?.("dialog") || dialog).close()));
  document.querySelectorAll("[data-open-dialog]").forEach((button) => button.addEventListener("click", () => document.getElementById(button.dataset.openDialog)?.showModal()));
  if (window.location.hash === "#rencana-saya") document.getElementById("rencana-saya")?.showModal?.();
  document.querySelectorAll("[data-replace-menu]").forEach((button) => button.addEventListener("click", async () => {
    resetDialog("Ganti menu", `Hari ${button.dataset.day} · ${button.dataset.label || ""} · sekarang ${button.dataset.name || ""}`);
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
        day: Number(button.dataset.day), meal: button.dataset.meal,
        total: Number(button.dataset.total) || 0, budget: Number(button.dataset.budget) || 0 };
      selector.replaceChildren();
      // Radio rows in the server's order: best fit for the nutrition target, then cheapest.
      data.recipes.forEach((recipe, index) => {
        const delta = Number(recipe.delta) || 0;
        deltas[recipe.recipe_code] = delta;
        const option = document.createElement("label");
        option.className = "option";
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "replacement";
        radio.value = recipe.recipe_code;
        radio.checked = index === 0;
        const name = document.createElement("span");
        name.className = "option-name";
        name.textContent = recipe.name;
        const change = document.createElement("span");
        change.className = delta < 0 ? "option-delta cheaper" : delta > 0 ? "option-delta pricier" : "option-delta";
        change.textContent = delta ? `${delta > 0 ? "+" : "−"}${rupiah(Math.abs(delta))}` : "Harga sama";
        option.append(radio);
        option.append(name);
        option.append(change);
        selector.append(option);
      });
      selector.value = data.recipes.length ? data.recipes[0].recipe_code : "";
      picker.hidden = false;
      previewButton.hidden = false;
      previewButton.disabled = !data.recipes.length;
      showPickedTotal();
      previewFeedback.textContent = data.recipes.length ? "" : "Belum ada menu lain yang masih masuk budget dan target gizi hari ini. Menu lama tetap dipertahankan.";
    } catch (error) { if (generation === dialogGeneration) previewFeedback.textContent = error.message; }
    finally { button.disabled = false; }
  }));

  selector.addEventListener("change", (event) => {
    if (event.target?.value) selector.value = event.target.value;
    proposal = null;
    resultPanel.hidden = true;
    applyButton.hidden = true;
    previewButton.hidden = false;
    previewFeedback.textContent = "";
    showPickedTotal();
  });

  async function applyProposal(data, body) {
    const result = await request(data.apply_url, body);
    globalThis.TakarKuy?.flash("Menu diganti di draft. Simpan untuk memakainya.");
    navigate(result.url);
  }
  previewButton.addEventListener("click", async () => {
    if (!replacement || !selector.value) return;
    const generation = dialogGeneration;
    proposal = null;
    resultPanel.hidden = true;
    previewFeedback.textContent = "Menghitung ulang belanja dan gizi…";
    previewButton.disabled = true;
    selector.disabled = true;
    try {
      const data = await request(replacement.url, { action: "replace", version: replacement.version,
        day: replacement.day, meal: replacement.meal, recipe: selector.value });
      if (generation !== dialogGeneration || !dialog.open) return;
      // Within budget the server's quote is applied at once; a higher budget needs approval.
      if (data.over_budget > 0) showProposal(data);
      else await applyProposal(data, {});
    }
    catch (error) { if (generation === dialogGeneration) previewFeedback.textContent = error.message; }
    finally { if (generation === dialogGeneration) { previewButton.disabled = false; selector.disabled = false; } }
  });

  applyButton.addEventListener("click", async () => {
    if (!proposal) return;
    applyButton.disabled = true;
    try {
      await applyProposal(proposal, proposal.over_budget > 0 ? { new_budget: budgetField.value } : {});
    } catch (error) { previewFeedback.textContent = error.message; globalThis.TakarKuy?.toast(error.message, "error"); }
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
        title: values.get("title"), starts_on: values.get("starts_on") || null, replace_original: replaceOriginal });
      globalThis.TakarKuy?.flash("Rencana tersimpan.");
      navigate(data.url);
    } catch (error) { feedback.textContent = error.message; globalThis.TakarKuy?.toast(error.message, "error"); feedback.scrollIntoView({ block: "center" }); }
    finally { buttons.forEach((button) => { button.disabled = false; }); }
  }));

  document.querySelectorAll("[data-delete-plan]").forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm(`Hapus rencana “${button.dataset.title}”? Stok pantry tidak berubah.`)) return;
    button.disabled = true;
    try { const data = await request(button.dataset.url, { version: Number(button.dataset.version) }); globalThis.TakarKuy?.flash(`Rencana “${button.dataset.title}” dihapus.`); navigate(data.url); }
    catch (error) { feedback.textContent = error.message; globalThis.TakarKuy?.toast(error.message, "error"); feedback.scrollIntoView({ block: "center" }); }
    finally { button.disabled = false; }
  }));

  const pending = document.getElementById("pending-plan-preview");
  if (pending) { resetDialog("Pratinjau perubahan"); showProposal(JSON.parse(pending.textContent)); }
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
          "X-CSRFToken": document.querySelector('[name="csrfmiddlewaretoken"]').value,
        },
        body: JSON.stringify({ version: Number(button.dataset.version), items }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `Request belum berhasil (kode ${response.status}).`);
      feedback.textContent = `${body.saved} bahan masuk ke Pantry. Atur lokasi/tanggal di Pantry bila perlu.`;
      globalThis.TakarKuy?.flash(feedback.textContent);
      location.reload();
    } catch (error) {
      feedback.textContent = error.message;
      globalThis.TakarKuy?.toast(error.message, "error");
      button.disabled = false;
    }
  });
})();

// Planner form: rupiah formatting, target rules, steppers, day tabs and the
// avoided-ingredient chips. Each enhances markup that already works without JavaScript.
(() => {
  document.querySelectorAll(".js-rupiah-input").forEach((input) => {
    const format = () => {
      // Leave a comma for the server to reject: stripping it would read
      // "150.000,00" as 15.000.000.
      if (input.value.includes(",")) return;
      input.value = input.value.replace(/\D/g, "").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    };
    input.addEventListener("input", format);
    format();
  });

  // "Seimbang" cannot be combined with the specific targets.
  const targets = Array.from(document.querySelectorAll('input[name="targets"]'));
  const balanced = targets.find((input) => input.value === "seimbang");
  if (balanced) {
    const specific = targets.filter((input) => input !== balanced);
    const sync = (changed) => {
      if (changed === balanced && balanced.checked) specific.forEach((input) => { input.checked = false; });
      else balanced.checked = !specific.some((input) => input.checked);
    };
    targets.forEach((input) => input.addEventListener("change", () => sync(input)));
    sync();
  }

  document.querySelectorAll("[data-stepper]").forEach((box) => {
    const input = box.querySelector("input");
    box.querySelectorAll("[data-step]").forEach((button) => {
      button.hidden = false;
      button.addEventListener("click", () => {
        const min = Number(input.min) || 1;
        const max = Number(input.max) || 99;
        const next = (Number(input.value) || min) + Number(button.dataset.step);
        input.value = String(Math.min(max, Math.max(min, next)));
      });
    });
  });

  document.querySelectorAll("[data-day-tabs]").forEach((tabs) => {
    const buttons = Array.from(tabs.querySelectorAll("[data-day-tab]"));
    const section = tabs.closest("section");
    const panels = Array.from(section.querySelectorAll("[data-day-panel]"));
    if (buttons.length < 2) return;
    const show = (day) => {
      buttons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.dayTab === day)));
      panels.forEach((panel) => { panel.hidden = panel.dataset.dayPanel !== day; });
    };
    tabs.hidden = false;
    section.classList.add("tabbed");
    buttons.forEach((button) => button.addEventListener("click", () => show(button.dataset.dayTab)));
    show(buttons[0].dataset.dayTab);
  });

  document.querySelectorAll("[data-avoid]").forEach((box) => {
    const field = box.querySelector('input[name="exclude_ingredients"]');
    const chips = box.querySelector("[data-avoid-chips]");
    const count = box.querySelector("[data-avoid-count]");
    if (!field || !chips) return;
    const terms = () => field.value.split(",").map((term) => term.trim()).filter(Boolean);
    const adder = document.createElement("div");
    adder.className = "avoid-add";
    const input = document.createElement("input");
    input.type = "text";
    input.id = `${field.id}-add`;
    input.placeholder = "misalnya udang";
    input.autocomplete = "off";
    const add = document.createElement("button");
    add.type = "button";
    add.className = "secondary-button";
    add.textContent = "Tambah";
    adder.append(input, add);
    field.after(adder);
    field.hidden = true;
    const label = box.querySelector(`label[for="${field.id}"]`);
    if (label) label.htmlFor = input.id;

    const render = () => {
      chips.replaceChildren(...terms().map((term) => {
        const chip = document.createElement("span");
        chip.className = "avoid-chip";
        chip.textContent = term;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "×";
        remove.setAttribute("aria-label", `Hapus ${term}`);
        remove.addEventListener("click", () => {
          field.value = terms().filter((other) => other !== term).join(", ");
          render();
          input.focus();
        });
        chip.append(remove);
        return chip;
      }));
      count.textContent = String(terms().length);
      count.hidden = !terms().length;
    };
    const push = () => {
      const known = new Set(terms().map((term) => term.toLowerCase()));
      const added = input.value.split(",").map((term) => term.trim()).filter((term) => term && !known.has(term.toLowerCase()));
      if (added.length) field.value = [...terms(), ...added].join(", ");
      input.value = "";
      render();
      input.focus();
    };
    add.addEventListener("click", push);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); push(); }
    });
    render();
  });
})();
