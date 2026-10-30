import { request } from "./api.mjs";
import { rupiah } from "./dom.mjs";
import { visit } from "./navigation.mjs";
import { renderProposal } from "./proposal_view.mjs";

function replacementOption(recipe, checked) {
  const delta = Number(recipe.delta) || 0;
  const option = document.createElement("label");
  option.className = "option";
  const radio = document.createElement("input");
  radio.type = "radio";
  radio.name = "replacement";
  radio.value = recipe.recipe_code;
  radio.checked = checked;
  const name = document.createElement("span");
  name.className = "option-name";
  name.textContent = recipe.name;
  const change = document.createElement("span");
  change.className = delta < 0 ? "option-delta cheaper" : delta > 0 ? "option-delta pricier" : "option-delta";
  change.textContent = delta ? `${delta > 0 ? "+" : "−"}${rupiah(Math.abs(delta))}` : "Harga sama";
  option.append(radio);
  option.append(name);
  option.append(change);
  return option;
}

// "Ganti menu" and "Ganti semua menu": pick, preview the server quote, then apply it to the draft.
export function initPlanDialog() {
  const dialog = document.getElementById("plan-dialog");
  const picker = document.getElementById("replacement-picker");
  const selector = document.getElementById("replacement-recipe");
  const resultPanel = document.getElementById("preview-result");
  const previewFeedback = document.getElementById("preview-feedback");
  const previewButton = document.getElementById("request-preview");
  const applyButton = document.getElementById("apply-preview");
  const budgetField = document.getElementById("new-budget");
  const pickerTotal = document.getElementById("picker-total");
  let replacement = null;
  let deltas = {};
  let proposal = null;
  // Bumped on every reset/close so a late response from an older request is ignored.
  let dialogGeneration = 0;
  dialog.addEventListener("close", () => { dialogGeneration += 1; proposal = null; });

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
    document.getElementById("preview-eyebrow").hidden = true;
    if (!dialog.open) dialog.showModal();
  }

  function showPickedTotal() {
    if (!replacement || !(selector.value in deltas)) return;
    pickerTotal.textContent = `Total belanja jadi ${rupiah(replacement.total + deltas[selector.value])} / ${rupiah(replacement.budget)}`;
  }

  function showProposal(data) {
    proposal = data;
    renderProposal(data);
  }

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
      data.recipes.forEach((recipe, index) => {
        deltas[recipe.recipe_code] = Number(recipe.delta) || 0;
        selector.append(replacementOption(recipe, index === 0));
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
    await visit(result.url, "Menu diganti di draft. Simpan untuk memakainya.");
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

  const pending = document.getElementById("pending-plan-preview");
  if (pending) { resetDialog("Ganti semua menu", "Menu disusun ulang dari pengaturan baru. Rencana lama tetap aman sampai kamu menekan Pakai."); showProposal(JSON.parse(pending.textContent)); }
}
