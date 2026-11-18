import { initAvoidChips } from "./avoid_chips.mjs";
import { bindNavigation, onSwap } from "./navigation.mjs";
import { initPantryPurchases } from "./pantry_purchases.mjs";
import { initPlanDialog } from "./plan_dialog.mjs";
import { initPlannerForm } from "./planner_form.mjs";
import { initSavedPlans } from "./saved_plans.mjs";

// Dijalankan saat halaman pertama dimuat dan setiap kali <main> diganti; dialog rencana hanya diinisialisasi jika ada.
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
