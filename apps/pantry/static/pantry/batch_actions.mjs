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

export function locationExpiry(source, current, estimate) {
  if (source === "legacy") return {mode: "auto", date: current};
  return ["label", "manual"].includes(source)
    ? {mode: "manual", date: current}
    : {mode: "auto", date: estimate.estimated_expires_on};
}

export function isAISuggestion(method) {
  return ["ai_perlu_periksa", "ai_cache_perlu_periksa", "ai_foto_perlu_periksa"].includes(method);
}

export function correctionConsent(dataset, checked = false) {
  return {accepted: checked === true, user_edited: dataset.userEdited === "true"};
}
