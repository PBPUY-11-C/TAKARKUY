import { canSwap, swap } from "./navigation.mjs";

function bindAsyncSubmit() {
  const plannerForm = document.querySelector(".planner-form");
  plannerForm?.addEventListener("submit", async (event) => {
    if (!canSwap()) return;
    event.preventDefault();
    const button = plannerForm.querySelector('[type="submit"]');
    button.disabled = true;
    button.textContent = "Menyusun…";
    const swapped = await swap(plannerForm.action, { method: "POST", body: new FormData(plannerForm) });
    if (!swapped) HTMLFormElement.prototype.submit.call(plannerForm);
  });
}

function bindRupiahInputs() {
  document.querySelectorAll(".js-rupiah-input").forEach((input) => {
    const format = () => {
      if (input.value.includes(",")) return;
      input.value = input.value.replace(/\D/g, "").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    };
    input.addEventListener("input", format);
    format();
  });
}

// "Seimbang" and the specific nutrition targets are mutually exclusive.
function bindTargets() {
  const targets = Array.from(document.querySelectorAll('input[name="targets"]'));
  const balanced = targets.find((input) => input.value === "seimbang");
  if (!balanced) return;
  const specific = targets.filter((input) => input !== balanced);
  const sync = (changed) => {
    if (changed === balanced && balanced.checked) specific.forEach((input) => { input.checked = false; });
    else balanced.checked = !specific.some((input) => input.checked);
  };
  targets.forEach((input) => input.addEventListener("change", () => sync(input)));
  sync();
}

function bindSteppers() {
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
}

function bindDayTabs() {
  document.querySelectorAll("[data-day-tabs]").forEach((tabs) => {
    const buttons = Array.from(tabs.querySelectorAll("[data-day-tab]"));
    const section = tabs.closest("section");
    const panels = Array.from(section.querySelectorAll("[data-day-panel]"));
    if (!buttons.length) return;
    const show = (day) => {
      buttons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.dayTab === day)));
      panels.forEach((panel) => {
        const inactive = panel.dataset.dayPanel !== day;
        panel.classList.toggle("is-inactive", inactive);
        panel.inert = inactive;
      });
    };
    tabs.hidden = false;
    section.classList.add("tabbed");
    buttons.forEach((button) => button.addEventListener("click", () => show(button.dataset.dayTab)));
    show(buttons[0].dataset.dayTab);
  });
}

export function initPlannerForm() {
  if (document.querySelector("[data-save-plan]")) {
    try { sessionStorage.setItem("takarkuy-planner", "1"); } catch (error) {  }
  }
  bindAsyncSubmit();
  bindRupiahInputs();
  bindTargets();
  bindSteppers();
  bindDayTabs();
}
