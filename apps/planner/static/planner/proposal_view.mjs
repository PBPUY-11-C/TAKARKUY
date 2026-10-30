import { element, rupiah } from "./dom.mjs";

function changeChip(before, after, unit) {
  const changed = before !== undefined && before !== null && Number(before) !== Number(after);
  return element("span", changed ? "proposal-chip changed" : "proposal-chip",
    changed ? `${before} → ${after} ${unit}` : `${after} ${unit}`);
}

function showDay(data, index) {
  const day = data.schedule[index];
  const tabs = document.getElementById("preview-day-tabs").children;
  Array.from(tabs).forEach((tab, position) => tab.setAttribute("aria-pressed", String(position === index)));
  document.getElementById("preview-schedule").replaceChildren(...day.meals.map((meal) => {
    const row = element("div", "proposal-meal");
    row.append(element("span", "meal-label", meal.label), element("span", "proposal-meal-name", meal.name));
    if (meal.cost !== undefined) row.append(element("span", "muted", rupiah(meal.cost)));
    return row;
  }));
  document.getElementById("preview-day-note").textContent = data.nutrition_targets_set
    ? `Hari ${day.number}: ${day.protein} g protein · ${day.calories} kkal / orang` : "";
}

// Fill the preview dialog with a server proposal: cost, budget, nutrition, days, and shopping.
export function renderProposal(data) {
  document.getElementById("preview-result").hidden = false;
  document.getElementById("request-preview").hidden = true;
  const applyButton = document.getElementById("apply-preview");
  applyButton.hidden = false;
  document.getElementById("preview-feedback").textContent = "";
  const eyebrow = document.getElementById("preview-eyebrow");
  eyebrow.textContent = data.title || "";
  eyebrow.hidden = !data.title;
  const mealLabels = (data.schedule[0]?.meals || []).map((meal) => meal.label).join(" · ");
  document.getElementById("preview-chips").replaceChildren(
    changeChip(data.previous_days, data.days, "hari"),
    changeChip(data.previous_servings, data.servings, "orang"),
    ...(mealLabels ? [element("span", "proposal-chip", mealLabels)] : []),
  );
  const delta = Number(data.delta);
  document.getElementById("preview-before").textContent = rupiah(data.before);
  document.getElementById("preview-after").textContent = rupiah(data.after);
  const cost = document.getElementById("preview-cost");
  cost.textContent = delta > 0 ? `Naik ${rupiah(delta)}` : delta < 0 ? `Turun ${rupiah(-delta)}` : "Total tetap";
  cost.className = delta > 0 ? "proposal-delta up" : delta < 0 ? "proposal-delta down" : "proposal-delta";
  const bar = document.getElementById("preview-bar");
  if (bar.style) bar.style.width = `${Math.min(100, Math.round((Number(data.after) / Number(data.budget)) * 100))}%`;
  bar.className = data.over_budget > 0 ? "over" : "";
  document.getElementById("preview-budget").textContent = data.over_budget > 0
    ? `Melebihi budget ${rupiah(data.budget)} sebesar ${rupiah(data.over_budget)}.`
    : `Sisa ${rupiah(data.budget - data.after)} dari budget ${rupiah(data.budget)}`;
  const status = document.getElementById("preview-status");
  status.textContent = data.over_budget > 0 ? "Melebihi budget" : "Dalam budget";
  status.className = data.over_budget > 0 ? "over" : "";
  const nutrition = data.nutrition || {};
  document.getElementById("preview-nutrition").replaceChildren(...[
    ["calories", "kkal / hari", ""], ["protein", "protein", " g"], ["carbs", "karbo", " g"], ["fat", "lemak", " g"],
  ].filter(([key]) => nutrition[key] !== undefined).map(([key, label, unit]) => {
    const box = element("div", "proposal-nutrient");
    box.append(element("strong", "", `${Number(nutrition[key]).toLocaleString("id-ID")}${unit}`), element("span", "", label));
    return box;
  }));
  document.getElementById("preview-notes").textContent = (data.preference_notes || []).join(" ");
  document.getElementById("budget-increase").hidden = data.over_budget <= 0;
  document.getElementById("new-budget").value = String(data.after);
  applyButton.textContent = data.over_budget > 0 ? "Naikkan budget & pakai" : "Pakai menu ini";

  document.getElementById("preview-day-tabs").replaceChildren(...data.schedule.map((day, index) => {
    const tab = element("button", "", `Hari ${day.number}`);
    tab.type = "button";
    tab.setAttribute("aria-pressed", String(index === 0));
    tab.addEventListener("click", () => showDay(data, index));
    return tab;
  }));
  showDay(data, 0);

  const icons = document.getElementById("shop-icons");
  document.getElementById("preview-summary").replaceChildren(...(data.summary || []).map((row) => {
    const item = element("li");
    const icon = element("span", `shop-icon shop-icon-${row.key}`);
    const svg = icons?.content?.querySelector(`[data-icon="${row.key}"]`);
    if (svg) icon.append(svg.cloneNode(true));
    const text = element("span", "shop-name", row.label);
    text.append(element("span", "muted", `${row.count} bahan`));
    item.append(icon, text);
    return item;
  }));
  const shopping = document.getElementById("preview-shopping");
  shopping.replaceChildren();
  let itemCount = 0;
  for (const group of data.shopping_groups) {
    for (const item of group.items) {
      itemCount += 1;
      const row = document.createElement("li");
      row.textContent = `${item.name}: ${item.quantity} g · ${rupiah(item.cost)}` +
        (item.purchase_units ? ` · beli ${item.purchase_units} ${item.purchase_unit}` : "");
      shopping.append(row);
    }
  }
  document.getElementById("preview-shopping-toggle").textContent = `Lihat semua ${itemCount} bahan`;
  const meals = data.schedule.reduce((total, day) => total + day.meals.length, 0);
  document.getElementById("picker-total").textContent = `${data.days} hari · ${meals} menu`;
}
