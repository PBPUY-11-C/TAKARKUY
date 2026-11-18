// Estimasi masa simpan lokasi terpilih (default suhu ruang); bila tak ada acuan, pesan isi manual.
export function storagePreview(storage, location) {
  const selected = location || "suhu_ruang";
  return storage?.options?.[selected] || {
    estimated_expires_on: "",
    shelf_life_days: null,
    message: "Acuan masa simpan untuk lokasi ini belum tersedia. Isi manual bila diketahui.",
  };
}
