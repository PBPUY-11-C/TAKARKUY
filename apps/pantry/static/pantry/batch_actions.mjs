// Pemberi operation_key per scope: payload sama memakai key lama agar retry tetap idempoten.
export function createActionKeyStore(newKey = () => crypto.randomUUID()) {
  const actions = new Map();
  return (scope, payload) => {
    const signature = JSON.stringify(payload);
    const previous = actions.get(scope);
    if (previous?.signature === signature) return previous.key;
    const key = newKey();
    actions.set(scope, {signature, key});
    return key;
  };
}

// Mode dan tanggal kedaluwarsa saat lokasi diganti; tanggal label/manual/lama dipertahankan.
export function locationExpiry(source, current, estimate) {
  if (source === "legacy") return {mode: "auto", date: current};
  return ["label", "manual"].includes(source)
    ? {mode: "manual", date: current}
    : {mode: "auto", date: estimate.estimated_expires_on};
}

// True bila saran nama berasal dari AI (langsung, cache, atau foto) sehingga perlu diperiksa.
export function isAISuggestion(method) {
  return ["ai_perlu_periksa", "ai_cache_perlu_periksa", "ai_foto_perlu_periksa"].includes(method);
}

// Menyusun flag persetujuan koreksi nama (accepted, user_edited) dari checkbox dan dataset baris.
export function correctionConsent(dataset, checked = false) {
  return {accepted: checked === true, user_edited: dataset.userEdited === "true"};
}
