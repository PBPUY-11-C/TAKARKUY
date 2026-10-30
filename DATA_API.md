# Data dan API TAKARKUY

Dokumen ini menjelaskan dataset yang dipakai aplikasi, asal dan lisensinya, cara memperbaruinya, serta API eksternal yang dipanggil. Angka di tabel dicek otomatis oleh `data/validate_docs.py` di CI.

## Struktur folder `data/`

| Folder / file | Isi | Dibaca aplikasi? |
|---|---|---|
| `fixtures/catalog_seed.json` | Katalog lengkap (bahan, harga, resep, tag, alergen) untuk `import_catalog` | Ya |
| `mapping/recipe_image_mapping.csv` | Foto resep berlisensi terbuka beserta kredit | Ya |
| `mapping/fruit_purchase_units.json` | Berat dan bagian termakan per buah utuh | Ya |
| `authored_instructions.json` | Langkah masak yang ditulis dan ditinjau tim | Ya, saat impor |
| `processed/`, `mapping/` | Tabel hasil olahan yang membentuk fixture | Tidak (sumber build) |
| `staging/`, `scratch/` | Kandidat dan audit kurasi | Tidak |
| `raw/` | Snapshot sumber asli; `raw/manifest.json` mencatat URL, ukuran, dan SHA-256 | Tidak |
| `*.py` | Skrip build dan validasi pipeline data | Tidak |

## Dataset aktif

| Dataset | Baris | Isi |
|---|---:|---|
| `processed/ingredients.csv` | 202 | Bahan; 164 punya empat makro. Sumber Bapanas, USDA, TKPI (lewat mirror/Mendeley), label produk, Open Food Facts. |
| `processed/ingredient_allergens.csv` | 202 | 9 kelompok alergen ([FSA](https://www.food.gov.uk/business-guidance/allergen-guidance-for-food-businesses)); bukan sertifikasi. |
| `processed/ingredient_prices.csv` | 164 | 78 harga Kabupaten Garut + 21 PIHPS (28 September 2026), ditambah 65 referensi toko daring non-Garut. Harga Garut diutamakan. |
| `processed/ingredient_shelf_life.csv` | 149 | Rentang lama simpan berbasis [USDA FoodKeeper](https://catalog.data.gov/dataset/fsis-foodkeeper-data); bukan tanggal kedaluwarsa kemasan. |
| `processed/recipes.csv` | 516 | **303 siap dihitung**: 87 internal, 18 adaptasi Kaggle, 7 TheMealDB, 191 Mendeley. 213 lainnya masih diblokir. |
| `processed/recipe_ingredients.csv` | 3.046 | Bahan dan gram per resep; takaran perkiraan ditandai `quantity_status=estimated`. |
| `processed/recipe_tags.csv` | 2.418 | Tag resep; label diet/halal bukan sertifikasi. |
| `mapping/ingredient_aliases.csv` | 381 | Alias nama bahan untuk pencocokan stok dan OCR. |
| `mapping/unit_conversions.csv` | 615 | Konversi satuan dan massa standar. |

Fixture `fixtures/catalog_seed.json` berisi **7.491 objek**. Resep yang siap dihitung punya gram, empat makro, dan harga untuk semua bahannya. Angka gizi yang tidak diketahui tidak diisi nol, dan semua estimasi atau proksi diberi label.

## Sumber dan lisensi

| Sumber | Dipakai untuk | Lisensi / catatan |
|---|---|---|
| [Purwanto, Wibawa & Devi — Mendeley Data v3](https://data.mendeley.com/datasets/8b4ztns76h/3) (DOI `10.17632/8b4ztns76h.3`) | 191 resep siap dihitung | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Teks langkah asli ditahan; aplikasi hanya memakai langkah yang ditulis tim. |
| [Bapanas — Tabel Komposisi Pangan Segar](https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia) | Gizi bahan segar | Data pemerintah |
| [Bapokting Kabupaten Garut](https://bapokting.disperindag.garutkab.go.id/Bapokting/) dan PIHPS Bank Indonesia | Harga bahan (snapshot 28 September 2026) | Data pemerintah; bukan harga real-time |
| [USDA FoodData Central](https://fdc.nal.usda.gov/download-datasets/) dan [FoodKeeper](https://catalog.data.gov/dataset/fsis-foodkeeper-data) | Gizi cadangan, konversi ukuran, lama simpan | CC0 / domain publik |
| [TheMealDB](https://www.themealdb.com/docs_api_guide.php) | 7 resep internasional yang diadaptasi | [Ketentuan API](https://themealdb.com/terms_of_use.php) |
| [Open Food Facts](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/) | Kandidat produk kemasan | ODbL, wajib atribusi |
| Kaggle Indonesian Food Recipes | 18 resep; langkahnya ditulis ulang tim | Arsip di `raw/` |
| Openverse / Wikimedia Commons / Flickr | Foto resep di `mapping/recipe_image_mapping.csv` | CC0, CC BY, CC BY-SA; kredit tampil di halaman Resep |
| Toko daring (Sayurbox, Tokopedia, UbiFresh, dll.) | Harga pelengkap bahan yang tidak ada di Garut | URL, harga, dan tanggal tinjauan di `mapping/mendeley_sources.json` |

## Memperbarui data

Dari root proyek:

```bash
python data/build_candidate_indexes.py
python data/build_final.py
python data/validate_candidates.py
python data/validate_catalog.py
python data/validate_docs.py
python manage.py import_catalog data/fixtures/catalog_seed.json --sync-generated-relations
```

`build_final.py` membangun ulang `processed/` dan fixture dari snapshot lokal tanpa mengakses internet. `import_catalog` memperbarui katalog dengan `update_or_create` dalam satu transaksi; data pengguna (stok, rencana, riwayat masak) tidak ikut terhapus. Setelah mengubah tabel aktif, perbarui angka di dokumen ini supaya `validate_docs.py` lolos.

## API eksternal saat aplikasi berjalan

| API | Modul | Cara kerja | Pengaturan |
|---|---|---|---|
| [Nominatim](https://nominatim.org/) dan [Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API) (OpenStreetMap) | Home (Dashboard) — pencarian pasar terdekat | Cache server 7 hari (`MapLookupCache`), kuota 10 pencarian per akun per 10 menit, jeda antar panggilan, timeout 8 detik. Jika server luar gagal atau dimatikan, daftar pasar kurasi tetap tampil. | `MAP_LOOKUP_ENABLED=true`, `MAP_USER_AGENT` (wajib berisi "TAKARKUY" dan URL/email) |
| [Gemini](https://ai.google.dev/) (`gemini-3.5-flash-lite`, diatur lewat `PANTRY_LLM_MODEL`) | Pantry — cadangan OCR struk dan pencocokan nama bahan | Dipanggil hanya saat Tesseract.js kurang yakin. Cache hasil 30 hari, kuota 10 panggilan per akun per hari, timeout 5–25 detik, foto maksimal 10 MB dan tidak disimpan. | `PANTRY_LLM_PROVIDER=gemini`, `GEMINI_API_KEY` |
| [Tesseract.js](https://github.com/naptha/tesseract.js) 7.0.0 | Pantry — OCR struk di browser | Library di sisi browser (bukan API server); dimuat dengan SRI. | — |

Tanpa pengaturan di atas, aplikasi tetap berjalan: peta memakai daftar pasar kurasi dan Pantry memakai Tesseract.js serta input manual.
