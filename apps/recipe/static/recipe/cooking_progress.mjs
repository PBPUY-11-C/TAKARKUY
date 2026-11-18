// Memulihkan progres mode memasak; null bila data rusak, resep berubah, atau jumlahnya tidak cocok.
export function restoreCookingProgress(storage, key, stepCount, ingredientCount, recipeFingerprint) {
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const progress = JSON.parse(raw);
    if (progress.recipeFingerprint !== recipeFingerprint) return null;
    if (!Number.isInteger(progress.step) || progress.step < 0 || progress.step >= stepCount) return null;
    if (!Array.isArray(progress.checked) || progress.checked.length !== ingredientCount) return null;
    if (!progress.checked.every(value => typeof value === 'boolean')) return null;
    return {step: progress.step, checked: progress.checked};
  } catch {
    return null;
  }
}

// Menyimpan progres ke storage; mengembalikan false bila storage tidak bisa ditulis.
export function saveCookingProgress(storage, key, step, checked, recipeFingerprint) {
  try {
    storage.setItem(key, JSON.stringify({step, checked, recipeFingerprint}));
    return true;
  } catch {
    return false;
  }
}

// Menghapus progres tersimpan; error storage diabaikan.
export function clearCookingProgress(storage, key) {
  try { storage.removeItem(key); }
  catch {  }
}
