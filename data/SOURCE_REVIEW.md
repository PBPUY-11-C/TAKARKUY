# Review sumber dan kebijakan publikasi

Ditinjau 5 Oktober 2026. Catatan ini membedakan kelengkapan hitungan, kualitas sumber, dan izin publikasi; ketiganya bukan hal yang sama. Tidak ada klaim sertifikasi halal atau jaminan akurasi medis/harga.

## Mendeley Data v3

- Judul: *Nutritional Analysis and Macro-Micro Nutrient Profiling of Indonesian Culinary Recipes*.
- Penyusun: Devi Dwi Purwanto, Aji Prasetya Wibawa, Mazarina Devi.
- Sumber: https://data.mendeley.com/datasets/8b4ztns76h/3 ; DOI `10.17632/8b4ztns76h.3`, 11 Mei 2026.
- Lisensi yang tercantum pada halaman dataset: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Atribusi, tautan lisensi, dan perubahan harus dipertahankan. Status ini bukan bukti tersendiri bahwa semua teks pihak ketiga di dalamnya telah mendapat izin.
- Perubahan TAKARKUY: normalisasi nama, mapping bahan/proksi, konversi/estimasi gram, massa beli/rendemen, penentuan slot, perhitungan ulang makro/biaya, serta penyaringan menu/non-halal/bahan hilang. Lihat `mendeley_recipes.py`, `mapping/mendeley_terms.csv`, `mapping/mendeley_sources.json` dan `staging/mendeley_recipe_audit.csv`.
- **Keputusan sekarang:** 187 resep dapat digunakan untuk simulasi estimasi. Teks langkah asli **ditahan**, termasuk dari snapshot rencana lama. Fixture/CSV aktif berisi langkah kosong dan metadata `withheld_pending_rights_review`; sumber mentah tidak dihapus. `is_plannable` bukan izin publikasi langkah.
- **Belum selesai:** asal teks langkah, kemungkinan pihak ketiga seperti Cookpad, serta cakupan izin penyusun. Ini belum dikonfirmasi, bukan tuduhan pelanggaran.
- **Syarat membuka langkah:** tim mendokumentasikan izin/asal teks per resep, atau menulis panduan sendiri dari fakta/metode memasak yang direview dan diuji, dengan atribusi sumber inspirasi. Jangan sekadar mengganti beberapa kata atau meminta LLM memparafrase teks sumber lalu menandainya telah disetujui. Saat proses review per-resep dibangun, tambahkan bukti, reviewer/tanggal, status dan tes publikasi; guard sekarang sengaja fail-closed untuk seluruh ID `RCP-MDL-*`.

## Gizi dan harga tambahan

14 bahan tambahan memakai nilai TKPI melalui dataset Mendeley; belum dicocokkan PDF TKPI asli. Bentuk/proksi (misalnya soun memakai pendekatan bihun jagung) tetap tercatat. Menghitung ulang makro bukan verifikasi nilai dasar atau hidangan jadi. Takaran rumah tangga, rendemen ikan, slot makan dan bumbu minor yang tidak dihitung adalah asumsi yang harus terlihat.

20 harga tambahan memakai listing Sayurbox dan Tokopedia, dengan URL, harga kemasan, massa/densitas/rendemen dan tanggal tinjauan dalam `mapping/mendeley_sources.json`. Bukan API publik atau harga Garut/live. Pemeriksaan ulang sesi ini tidak dapat mengakses beberapa listing; jangan menyatakan seluruh harga telah diverifikasi independen. Untuk produksi, reviewer perlu menyimpan bukti tanggal/ukuran kemasan/harga/status tersedia dan mengganti referensi yang tidak dapat diverifikasi, tanpa menimpa harga Garut.

## Sumber lainnya

Kaggle memakai langkah adaptasi tim, bukan penerbitan ulang verbatim. TheMealDB harus mengikuti ketentuan API. FoodKeeper berasal dari mirror historis dan perlu verifikasi kondisi lokal. Open Food Facts adalah kandidat komunitas berlisensi ODbL; jangan otomatis menjadikan semua SKU data generik yang terverifikasi. Rincian tautan/batas masing-masing ada di `README.md` dan `DATASETS.md`.

Kebijakan di atas mengurangi paparan teks yang belum direview, tetapi tidak menggantikan pemeriksaan hak pakai untuk rilis publik dataset mentah atau konten lain di repositori.
