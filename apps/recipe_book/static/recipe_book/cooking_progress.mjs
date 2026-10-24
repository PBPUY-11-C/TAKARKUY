export function restoreCookingProgress(storage, key, stepCount, ingredientCount) {
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const progress = JSON.parse(raw);
    if (!Number.isInteger(progress.step) || progress.step < 0 || progress.step >= stepCount) return null;
    if (!Array.isArray(progress.checked) || progress.checked.length !== ingredientCount) return null;
    if (!progress.checked.every(value => typeof value === 'boolean')) return null;
    return {step: progress.step, checked: progress.checked};
  } catch {
    return null;
  }
}

export function saveCookingProgress(storage, key, step, checked) {
  try {
    storage.setItem(key, JSON.stringify({step, checked}));
    return true;
  } catch {
    return false;
  }
}

export function clearCookingProgress(storage, key) {
  try { storage.removeItem(key); }
  catch { /* Session storage can be disabled; mode still works without persistence. */ }
}
