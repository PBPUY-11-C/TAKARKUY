// Menskalakan nilai dari porsi dasar ke porsi target 1 sampai 10; null bila input tidak valid.
export function scaleServings(value, baseServings, servings) {
  const amount = Number(value);
  const base = Number(baseServings);
  const target = Number(servings);
  if (!Number.isFinite(amount) || !Number.isInteger(base) || base < 1 || !Number.isInteger(target) || target < 1 || target > 10) {
    return null;
  }
  return amount * target / base;
}

// Membulatkan angka ke jumlah desimal tertentu; null bila bukan angka hingga.
export function roundedAmount(value, digits = 1) {
  if (!Number.isFinite(value)) return null;
  return Number(value.toFixed(digits));
}
