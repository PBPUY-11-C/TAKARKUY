# Dataset TAKARKUY untuk MVP

Harga Garut dan sumber gizi inti memakai snapshot **28 September 2026**. Tambahan estimasi/referensi toko daring dicatat pada **1 dan 5 Oktober 2026**; inventaris diperbarui **5 Oktober 2026**. Delapan CSV utama terhubung melalui ID stabil. Perkiraan dicatat sebagai `estimated`, bukan angka sumber terverifikasi; bahan/gizi/harga yang belum dapat dipadankan tetap diblokir. Inventaris lengkap ada di `DATASETS.md`; keputusan publikasi ada di `SOURCE_REVIEW.md`.

| File | Baris | Kegunaan |
|---|---:|---|
| `processed/ingredients.csv` | 201 | Master bahan; 163 memiliki empat makro, termasuk proksi/transkripsi yang diberi status |
| `processed/ingredient_prices.csv` | 163 | 78 Garut, 21 PIHPS, 64 referensi toko daring non-Garut |
| `processed/ingredient_shelf_life.csv` | 149 | Acuan FoodKeeper untuk 80 bahan; **bukan tanggal kedaluwarsa produk** |
| `processed/recipes.csv` | 434 | 296 siap dihitung: 87 internal, 18 adaptasi Kaggle, 4 TheMealDB, 187 Mendeley; 138 diblokir. Langkah Mendeley ditahan |
| `processed/recipe_ingredients.csv` | 2.973 | Gram kurasi/estimasi; `raw_text` menyimpan provenance estimasi dan massa beli |
| `processed/recipe_tags.csv` | 2.140 | Tag resep kurasi, estimasi, dan kategori/saran slot kandidat |
| `mapping/ingredient_aliases.csv` | 376 | Nama bahan dari harga, gizi, dan aturan kurasi |
| `mapping/unit_conversions.csv` | 612 | Massa standar dan konversi spesifik; kemasan tanpa bobot aman tetap tidak dapat dipakai |

Hitungan tabel bersifat snapshot; jalankan `python3 data/validate_catalog.py` dan `python3 data/validate_docs.py` dari akar proyek untuk memeriksa ulang. `fixtures/catalog_seed.json` memuat 7.048 objek dan identik dengan fixture aplikasi. `dataset_counts.json`, `processed/recipe_readiness.csv` (434 baris), `processed/recipe_estimated_nutrition.csv` (296 baris), serta audit estimasi dibuat otomatis. Audit Kaggle/TheMealDB memuat 1.824 baris bahan/komponen dari 160 kandidat; audit Mendeley terpisah di `staging/mendeley_recipe_audit.csv`.

Promosi kandidat memperbarui resep dengan ID yang sama; bahan berulang dijumlahkan menjadi satu relasi. Generator/importer merangkum salinan identik dan menolak ID sama dengan isi berbeda. Kurasi nama/kelayakan mengeluarkan 48 resep dari ekspansi sebelumnya; alasan normalisasi/pengecualian ada di `mapping/recipe_name_overrides.csv`, bukan penghapusan sumber mentah. Nama resep aktif ganda ditolak. Importer juga menghapus badge kandidat/saran slot yang usang pada resep yang dipromosikan, tanpa menghapus tag pengguna atau riwayat rencana.

## Sumber dan jejak angka

- [Mendeley Data v3 — Purwanto, Wibawa & Devi](https://data.mendeley.com/datasets/8b4ztns76h/3): 187 resep dipromosikan melalui `mendeley_recipes.py`. Lisensi dataset [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) dicatat dengan atribusi dan perubahan. Takaran/bentuk bahan dipadankan ke katalog, slot makan diestimasi, gizi dihitung ulang dari bahan. Teks langkah sumber tidak dimasukkan fixture; raw snapshot dipertahankan untuk review. Siap dihitung tidak sama dengan siap panduan memasak. Aturan/proksi/audit ada di `mapping/mendeley_terms.csv`, `mapping/mendeley_sources.json`, `staging/mendeley_recipe_audit.csv`, serta `SOURCE_REVIEW.md`.
- Harga tambahan [Sayurbox](https://www.sayurbox.com/p/labu-siam-ggdkmboo) dan [Tokopedia](https://www.tokopedia.com/kiossayurmakhaji/kelapa-parut-segar-250-gram): 20 referensi dengan URL/ukuran kemasan/tanggal tinjauan dalam `mapping/mendeley_sources.json`. Ditambah 44 referensi sebelumnya menjadi 64. Bukan harga Garut, bukan harga real-time, belum menghitung seluruh kemasan/ongkir. Akses ulang beberapa listing dibatasi; tidak semua harga telah diverifikasi ulang secara independen.

- [Komposisi Pangan Segar Indonesia, Badan Pangan Nasional](https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia): 64 bahan segar dalam `mapping/bapanas_nutrition_snapshot.json`. Nilai protein, lemak, dan karbohidrat disalin dari tabel per 100 g; kalori **diturunkan** dengan pendekatan 4-4-9 karena halaman sumber tidak menyediakan energi. `nutrition_source_id` dengan awalan `row:` adalah ID baris internal yang dibuat dari nama bahan, bukan kode resmi Bapanas. `nutrition_verified=true` berarti nilai makro dipadankan langsung dengan nama pada tabel, bukan bahwa kalori telah diukur.
- [TKPI Kemenkes](https://repository.kemkes.go.id/book/668): PDF lokal masih berupa pindai. Transkripsi/proksi memakai [mirror TKPI 2019](https://alatpertanian.asia/tabel-komposisi-pangan-indonesia-tkpi-2019/), **belum dicocokkan PDF asli**, sehingga `nutrition_verified=false` dan sumber menyebut mirror. Dori memakai proksi patin GR060, bukan klaim semua dori adalah patin. Daun salam segar diestimasi dari bubuk kering NR017 (air 13,1%) dengan **asumsi** kadar air segar 70%; bukan nilai TKPI segar atau hasil laboratorium. Tapioka memakai BP070. Angka USDA tetap dilabeli USDA.
- [USDA FoodData Central SR Legacy](https://fdc.nal.usda.gov/download-datasets/): fallback untuk beberapa bahan seperti tahu, tempe, garam, gula, dan bawang bombai. FDC ID ada pada `nutrition_source_id`; padanan pangan Indonesia diberi `nutrition_verified=false`.
- [Bapokting Disperindag Kabupaten Garut](https://bapokting.disperindag.garutkab.go.id/Bapokting/): harga 28 September 2026 dari laman komoditas. `source_url` menunjuk grafik komoditas masing-masing. Satuan yang diterbitkan dipertahankan; resep siap hitung divalidasi mempunyai harga bahan dalam `kg`. Lisensi penggunaan ulang tidak disebutkan pada laman yang diakses.
- [PIHPS Bank Indonesia](https://www.bi.go.id/hargapangan/Website/Home/Index/widget): 21 harga agregat nasional 28 September 2026, disimpan sebagai wilayah `Nasional PIHPS`. Data ini tidak diartikan sebagai harga Garut atau Depok. [FAQ PIHPS](https://www.bi.go.id/hargapangan/Informasi/FAQ) menjelaskan metode survei dan komoditas.
- [Open Data Bapanas](https://data.badanpangan.go.id/datasetpublications?category=3) dan [Panel Harga Bapanas](https://dev-panelharga.badanpangan.go.id/) diperiksa, tetapi tidak memberikan snapshot harga Depok/September 2026 yang bisa diunduh dan dicocokkan saat paket dibuat. Tidak ada harga Depok rekaan.
- [Indonesian Food Recipes di Kaggle](https://www.kaggle.com/datasets/canggih/indonesian-food-recipes): 60 kandidat diambil dari arsip. Bahan/takarannya diaudit; 18 aktif memakai langkah adaptasi TAKARKUY, bukan salinan langkah Cookpad verbatim. Sebanyak 87 resep internal tetap merupakan varian yang ditulis tim (20 inspirasi Kaggle, 67 internal lainnya), dengan takaran/porsi demonstrasi. Periksa izin sebelum menerbitkan ulang konten sumber verbatim.
- [TheMealDB API](https://www.themealdb.com/docs_api_guide.php): antrean sarapan lama (26 kandidat) tetap terpisah dari snapshot 100 kandidat `scratch/themealdb_100_candidates.json`; jangan menjumlahkannya tanpa deduplikasi sumber. **4 dari 100** kini siap dihitung dengan takaran/porsi estimasi. [Ketentuan API](https://themealdb.com/terms_of_use.php) ditinjau untuk demonstrasi; publikasi komersial/app store tetap perlu mengikuti ketentuannya. `fetch_themealdb.py` mengganti antrean, bukan otomatis mempromosikan semua resep.
- `mapping/themealdb_recipe_curation.csv` tetap pintu masuk **review manual**. Gunakan satu baris per bahan, ID sumber tetap, gram bagian termakan, porsi dan langkah lengkap; `approved` memerlukan ketiga flag review `true`. Review ini mengalahkan estimasi otomatis. `build_final.py` menolak approved tanpa empat makro/harga gram/metadata, dan mengganti metadata kandidat dengan ID sama.
- `recipe_estimation.py` membangun varian estimasi deterministik dari 160 kandidat berdasarkan izin pengguna. Konversi oz/lb memakai [NIST](https://www.nist.gov/pml/owm/metric-si/unit-conversion/approximate-conversions-us-customary-measures-metric); bobot rumah tangga mengacu USDA/[King Arthur](https://www.kingarthurbaking.com/learn/ingredient-weight-chart) plus asumsi lokal yang dilabeli. `secukupnya` diberi gram khusus bahan/batch, bukan satu angka universal. Porsi minimal 2, diestimasi menggunakan pembagi 150 g bahan protein hewani/75 g beras-tepung; bukan kebutuhan gizi manusia. Semua bahan sumber tetap ada di audit, termasuk penghalang dan air/alat yang dikecualikan.
- `mapping/recipe_estimation_sources.json` mencatat gizi tambahan dan 44 harga referensi non-Garut beserta kemasan, URL, tanggal tinjauan dan asumsi rendemen/densitas. `source_recorded_at` harga toko kosong karena tanggal publikasi tidak diketahui. `retail_reference` **hanya** mengisi bahan yang belum punya harga Garut pada snapshot; tidak menggantikan harga lokal. TokoWahab mentega adalah referensi grosir/stok habis, bukan harga eceran pasti; daun salam Pasar Rakyat Bali adalah listing historis saat situs tidak lagi menerima pesanan.
- Daun jeruk memakai label produk beku [Cock Brand/CT Food](https://ctfood.se/lime-leaf-frozen-30x114g-cock-brand/?language=en). Kaldu ayam bubuk memakai proksi USDA, bukan nilai label Royco. Kecap manis memakai satu SKU Bango dari [Open Food Facts](https://world.openfoodfacts.org/product/8999999002503) di snapshot lokal; kelengkapan empat makro tidak menjamin data komunitas benar. Proksi ini dilabeli dan tidak mengubah semua SKU menjadi satu bahan/gizi.
- [USDA FoodKeeper](https://catalog.data.gov/dataset/fsis-foodkeeper-data): sumber konsep lama simpan. Unduhan resmi mengembalikan 403 saat akses; angka pada CSV ini diambil dari [mirror arsip FoodKeeper](https://github.com/jelera/food-shelflife-db/blob/master/lib/seeds/ingredients.csv) dan dipadankan secara manual ke bahan Indonesia. Status semua baris `referensi_perlu_verifikasi_lokal`. Nilai bulan/tahun dikonversi menjadi hari dengan 30/365 hari. `warning_days` adalah kebijakan TAKARKUY: 10% dari batas minimum, dibulatkan, minimum 1 dan maksimum 14 hari; **bukan angka FoodKeeper**.
- [USDA SR Legacy food portions](https://fdc.nal.usda.gov/food-details/171287/nutrients) mendukung 50 g bagian dimakan untuk telur ukuran *large*; [bawang putih](https://fdc.nal.usda.gov/food-details/169230/nutrients) 3 g per siung menurut ukuran basis data. Keduanya bukan ukuran semua produk lokal.

## Pemakaian aman untuk Modul 1 dan Modul 2

Hanya pilih `recipes.is_plannable=true`. Setiap resep memiliki porsi dasar positif (tidak selalu 2), waktu makan, gram positif dengan status `curated`/`estimated`, empat makro, dan harga gram yang dapat dihitung. Harga/kg = `price_rupiah / quantity_kg`; biaya bahan = `SUM(purchase_quantity_g / 1000 * harga_per_kg)` bila audit memuat massa beli, selain itu memakai `quantity_g`. Jangan menganggap setiap baris harga menyatakan tepat 1 kg: referensi toko mempertahankan harga kemasan dan massa kemasannya. Makro/porsi = `SUM(quantity_g / 100 * macro_per_100g) / base_servings` dari bagian termakan. Contoh `RCP-MVP-001` tetap Rp7.984,22/2 porsi menurut snapshot Garut. Garam tercantum ikut dihitung pada resep estimasi; air utilitas, susut masak, kemasan utuh, dan ongkir tidak masuk. UI menandai penggunaan estimasi takaran, gizi proksi, rendemen ayam utuh, atau referensi harga non-Garut.

Untuk pisang, jeruk, dan melon, biaya aplikasi tidak lagi berhenti pada gram resep: `mapping/fruit_purchase_units.json` mengonversi kebutuhan gabungan seluruh hari menjadi perkiraan buah utuh, lalu menghitung biaya dari massa beli × harga Garut/kg. Berat dan rendemen buah adalah proksi [USDA Food Buying Guide](https://foodbuyingguide.fns.usda.gov/files/Reports/USDA_FBG_Section3_Fruits_YieldTable.pdf), bukan pengamatan gerai lokal. Daftar belanja menampilkan jumlah buah, massa utuh perkiraan, dan sisa bagian termakan. Harga pasar Garut tidak boleh dilabeli harga supermarket; jika tersedia data gerai dan ukuran kemasan aktual, ganti proksi ini dengan penawaran toko yang tercatat sumber/tanggalnya.

Masih ada **42 Kaggle dan 96 TheMealDB** yang diblokir; lihat `recipe_readiness.csv`. Banyak gram dapat diestimasi, tetapi bumbu campuran, bentuk pangan, gizi/harga belum lengkap. Parser memecah bahan gabungan yang jelas tanpa menghilangkan komponen tak dikenal. Takaran bersama seperti “1 sdm garam dan gula” tidak digandakan; makanan matang tidak diberi gizi daging mentah. Gram yang diketahui tetap diaudit meski belum punya padanan, tetapi tidak dipakai planner. Gizi kosong bukan nol. Ayam `1 ekor` memakai **asumsi** 1.000 g massa beli (jumbo 1.500 g) dan 60% bagian termakan; biaya memakai massa beli, gizi bagian termakan. Ini bukan berat aktual ayam pengguna. Pada 1 Oktober aturan v2 menaikkan siap hitung 93 → 108; ekspansi berikutnya menaikkan total menjadi 296. Review tidak otomatis mengaktifkan semua kandidat.

Tag `halal` adalah **heuristik daftar bahan**, bukan sertifikasi produk, bumbu, proses, atau dapur. `vegetarian` dan tag makro/alergen pada resep internal bukan pengujian klinis/sertifikasi; planner menghitung makro dari gram, tidak hanya percaya tag. Tag internal `tinggi_protein` (20 g/porsi) dan `rendah_kalori` (400 kkal/porsi) bukan syarat harian runtime. Produk olahan/gizi proksi dan kontaminasi silang memerlukan verifikasi untuk keputusan diet penting.

Data FoodKeeper merupakan panduan lama simpan berdasarkan kondisi sumber. Untuk Modul 2, tampilkan sebagai rentang **referensi** dan minta tanggal pembelian/penyimpanan dari pengguna. Jangan jadikan `max_days` sebagai jaminan makanan aman. Saat produk lokal, suhu aktual, kemasan, atau tanggal label tersedia, utamakan data tersebut. `starting_event` menjelaskan tanggal awal setiap durasi.

`base_unit` adalah gram. Konversi `g`, `kg`, dan `ons` berlaku sebagai satuan massa (1 ons Indonesia = 100 g). Konversi `butir` hanya untuk telur ukuran *large* dan `siung` untuk ukuran USDA, berstatus `size_specific`. Baris `ikat` dan `pack` berstatus `unusable` dan bobotnya kosong; aplikasi harus meminta bobot kemasan/hasil timbang SKU yang tepat sebelum menghitung. Harga dengan satuan `liter`, `bungkus`, `pcs`, dan sejenisnya juga memerlukan konversi produk spesifik sebelum digabung dengan resep gram.

## Struktur dan cara membangun ulang

`raw/` menyimpan snapshot sumber yang diperoleh; aplikasi membaca `processed/` dan `mapping/` saja. `mapping/bapanas_nutrition_snapshot.json` dan `mapping/garut_price_snapshot.csv` adalah hasil ekstraksi sumber. Jalankan dari direktori `data/`:

```bash
python3 build_final.py
python3 validate_catalog.py
```

Untuk mengambil kandidat resep publik, jalankan dari akar proyek:

```bash
python3 data/fetch_themealdb.py
```

Perintah ini hanya membuat snapshot JSON dan antrean review CSV; tidak menambah baris aktif ke planner. Setelah kandidat diperiksa, petakan resep yang lolos ke `mapping/themealdb_recipe_curation.csv`, lalu jalankan `python3 data/build_final.py`, `python3 data/validate_catalog.py`, dan impor ulang `data/fixtures/catalog_seed.json`. Planner tidak menelepon API setiap kali user menghitung menu; hasil API yang belum diverifikasi tidak akan memengaruhi biaya/gizi.

Skrip pembangun perlu arsip `raw/indonesian_food_recipes.zip` dan `raw/usda_sr_legacy_2018-04.zip`; jaringan tidak diperlukan ketika snapshot sudah tersimpan. Perbarui snapshot sumber dan petanya secara sadar sebelum membangun ulang. `ingredient_code` tidak boleh dihasilkan lagi dari ejaan baru tanpa migrasi karena sudah menjadi kunci penghubung.

## Impor Django

App katalog sudah ditempatkan di proyek pada `apps/catalog/`, dengan `models.py`, command `import_catalog.py`, dan paket `apps/__init__.py`. Di `settings.py`:

```python
INSTALLED_APPS += ["apps.catalog"]
```

Lalu jalankan dari akar proyek:

```bash
python manage.py makemigrations catalog
python manage.py migrate
python manage.py loaddata data/fixtures/catalog_seed.json
```

Jika proyek memiliki model katalog sendiri, sesuaikan model dan label fixture terlebih dahulu. Primary key fixture stabil, sehingga `loaddata` dengan key yang sama umumnya memperbarui objek. Jangan mengubah primary key secara manual. Untuk pembaruan dataset besar dan penonaktifan resep yang hilang, gunakan `python manage.py import_catalog data/fixtures/catalog_seed.json --deactivate-missing-recipes`; perintah ini melakukan `update_or_create` dalam transaksi. Tinjau efek `--deactivate-missing-recipes` sebelum menggunakannya pada database produksi.

`BudgetPlan` dan `ShoppingListItem` tetap disimpan sebagai data pengguna di database, bukan di CSV ini.

Catatan panjang metode gizi kini memakai `TextField`, sehingga tidak terpotong/ditolak oleh PostgreSQL. Jalankan `python manage.py migrate --noinput` sebelum impor pada environment yang belum menerima migrasi `catalog.0002_ingredient_calories_method_text`. Importer memeriksa panjang kolom lain sebelum menulis. Hasil audit, file yang sengaja dipertahankan, dan batas verifikasi produksi ada di bagian audit `DATASETS.md`.

Untuk menyinkronkan relasi katalog yang sebelumnya sudah diimpor, gunakan **fixture lengkap**, bukan potongan:

```bash
python manage.py import_catalog data/fixtures/catalog_seed.json --sync-generated-relations
```

Opsi ini menghapus relasi bahan/tag buatan generator yang tidak lagi tercantum, **hanya pada resep dalam fixture**. Sumber relasi pengguna, resep lain, stok pantry dan riwayat rencana tetap dipertahankan. Tanpa opsi ini, relasi lama tidak dihapus (kecuali badge kandidat/saran slot yang usang pada promosi). Selalu tinjau fixture sebelum menjalankan opsi sinkronisasi pada produksi.
