const NON_ITEM = /\b(?:sub\s*total|grand\s*total|total|hemat|disc(?:ount)?|diskon|potongan|ppn|pajak|bkp|dpp|pembayaran|tunai|cash|kembali|change|npwp|tanggal|kasir|member|nomor|invoice|receipt|telp|telepon|alamat|qty|harga|deskripsi|debit|kredit|master|visa|terima\s+kasih)\b/i;
const UNIT_ALIASES = {
  g: "g", gr: "g", gram: "g", kg: "kg", ml: "ml", l: "liter", liter: "liter",
  buah: "buah", pcs: "buah", pc: "buah", ikat: "ikat", butir: "butir",
  papan: "pack", kotak: "pack", box: "pack", bungkus: "pack",
  bks: "pack", botol: "botol", pack: "pack", pak: "pack",
};

export function parseReceiptText(text) {
  if (typeof text !== "string") return [];
  const result = [];
  for (const original of text.slice(0, 20000).split(/\r?\n/)) {
    const line = original.replace(/\s+/g, " ").trim();
    if (!line || NON_ITEM.test(line) || !/[A-Za-z]/.test(line)) continue;

    const tokens = line.replace(/^\d{8,14}\s+/, "").split(" ");
    let priceTokens = 0;
    while (tokens.length && priceTokens < 2 && /^(?:(?:Rp)?-?\d{1,3}(?:[.,]\d{3})+|\d{4,8})$/i.test(tokens.at(-1))) {
      tokens.pop();
      priceTokens += 1;
    }
    const hasExplicitUnit = UNIT_ALIASES[tokens.at(-1)?.toLowerCase().replace(/[^a-z]/g, "") || ""]
      && /^\d+(?:[.,]\d+)?$/.test(tokens.at(-2) || "");
    // When OCR misses the price, keep an apparent item with a small quantity as an editable draft.
    const hasQuantityOnly = tokens.length >= 3 && /^\d{1,3}(?:[.,]\d{1,2})?$/.test(tokens.at(-1) || "");
    if (!priceTokens && !hasExplicitUnit && !hasQuantityOnly) continue;
    if (tokens.at(-1)?.toLowerCase() === "rp") tokens.pop();

    let unit = "";
    let quantity = "";
    const last = tokens.at(-1)?.toLowerCase().replace(/[^a-z]/g, "") || "";
    if (UNIT_ALIASES[last] && /^\d+(?:[.,]\d+)?$/.test(tokens.at(-2) || "")) {
      unit = UNIT_ALIASES[last];
      quantity = tokens.at(-2).replace(",", ".");
      tokens.splice(-2);
    } else if (/^\d+(?:[.,]\d+)?$/.test(tokens.at(-1) || "")) {
      quantity = tokens.pop().replace(",", ".");
    }

    const name = tokens.join(" ").replace(/^[^A-Za-z]+|[^A-Za-z0-9)]+$/g, "").trim();
    if (name.length < 3 || !/[A-Za-z]{2}/.test(name) || /^\d/.test(name)) continue;
    result.push({ rawLine: line, name, quantity, unit });
    if (result.length >= 30) break;
  }
  return result;
}
