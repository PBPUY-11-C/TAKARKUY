import { initAvoidChips } from "./avoid_chips.mjs";
import { bindNavigation, onSwap } from "./navigation.mjs";
import { initPantryPurchases } from "./pantry_purchases.mjs";
import { initPlanDialog } from "./plan_dialog.mjs";
import { initPlannerForm } from "./planner_form.mjs";
import { initSavedPlans } from "./saved_plans.mjs";

// Runs on first load and again after every <main> swap.
function init() {
  if (document.getElementById("plan-dialog")) {
    initPlanDialog();
    initSavedPlans();
  }
  initPantryPurchases();
  initPlannerForm();
  initAvoidChips();
}

onSwap(init);
bindNavigation();
init();
