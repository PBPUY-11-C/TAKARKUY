# Inventaris dataset TAKARKUY

Snapshot diperiksa pada **1 Oktober 2026**. Angka di sini menunjukkan baris data, bukan jumlah makanan unik yang sudah siap digunakan. Ada tiga tingkat: **aktif** (`processed/` dan `mapping/`, dipakai aplikasi), **kandidat** (`staging/` dan `scratch/`, hanya untuk kurasi), dan **sumber mentah** (`raw/`, untuk jejak asal dan rekonstruksi). Tidak ada klaim bahwa katalog telah mencakup seluruh bahan Indonesia atau seluruh produk minimarket.

## Dataset aktif

| Dataset | Baris | Fungsi dan batasnya |
|---|---:|---|
| `processed/ingredients.csv` | 187 | Nama/ID bahan; **146** memiliki empat makro. Sumber [Bapanas](https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia), [USDA](https://fdc.nal.usda.gov/download-datasets/), transkripsi/proksi TKPI melalui mirror, label produk, serta satu produk Open Food Facts; semuanya dengan sumber/status. Tidak ada klaim cakupan seluruh bahan Indonesia. |
| `processed/ingredient_prices.csv` | 143 | 78 Garut + 21 PIHPS (28 September 2026), ditambah **44 referensi toko daring non-Garut** yang ditinjau 1 Oktober 2026. Tanggal terbit listing tidak diketahui; bukan harga real-time. Harga Garut tetap diutamakan. |
| `processed/ingredient_shelf_life.csv` | 149 | Rentang lama simpan untuk 80 bahan/berbagai kondisi. Berbasis [USDA FoodKeeper](https://catalog.data.gov/dataset/fsis-foodkeeper-data) melalui mirror historis; semua perlu verifikasi lokal. **Bukan** tanggal kedaluwarsa pada kemasan. |
| `processed/recipes.csv` | 247 | **108 siap dihitung**: 87 internal (termasuk 2 dori proksi patin), 17 adaptasi Kaggle, 4 TheMealDB. **139** masih diblokir. |
| `processed/recipe_ingredients.csv` | 625 | Hubungan bahan dan gram; takaran tambahan memakai `quantity_status=estimated` beserta audit di `raw_text`. Bahan berulang dalam resep dijumlahkan menjadi satu relasi/ID. |
| `processed/recipe_tags.csv` | 915 | Tag resep; label diet/halal bukan sertifikasi. Tag kandidat dibersihkan saat promosi. |
| `mapping/ingredient_aliases.csv` | 362 | Padanan nama bahan/alias; ID lama dipertahankan agar relasi stok tidak putus. |
| `mapping/unit_conversions.csv` | 570 | Massa standar dan konversi spesifik. Asumsi takaran resep **tidak** menjadi konversi kemasan global untuk OCR/pantry. |
| `staging/recipe_quantity_estimates.csv` | 1.824 | Audit **semua bahan dari 160 kandidat**, termasuk 38 komponen tambahan hasil pemisahan bahan gabungan: nama/takaran asli, gram termakan dan massa beli jika dapat dihitung, padanan bahan, asumsi, sumber, dan penghalang. Baris `blocked` dapat memiliki gram yang diketahui tetapi belum punya padanan gizi/harga. |
| `processed/recipe_readiness.csv` | 247 | Status/penyebab per resep; memudahkan memilih penghalang yang perlu dilengkapi. |
| `processed/recipe_estimated_nutrition.csv` | 108 | Hasil perhitungan empat makro dan biaya per porsi resep siap hitung; bukan hasil uji laboratorium. |

`fixtures/catalog_seed.json` berisi **3.198 objek** dan identik dengan fixture aplikasi. Delapan tabel utama dan kedua fixture lolos pemeriksaan PK/FK tanpa ID ganda. Kandidat yang dipromosikan **mengganti metadata dengan ID sama**, bukan ditambahkan lagi. Duplikat identik diringkas; ID sama dengan isi berbeda ditolak, bukan diam-diam ditimpa. Tidak ada penghapusan resep hanya karena judulnya mirip.

### Estimasi baru dan 139 resep yang masih diblokir

| Kelompok | Jumlah | Penghalang utama |
|---|---:|---|
| TheMealDB | 4 aktif / 96 diblokir | Aktif: Bread Omelette, Algerian Kefta, Fasoliyyeh, Algerian Flafla. Semua porsi/takaran rumah tangga diberi label estimasi. Sisanya masih memiliki padanan bahan/bentuk produk, harga, satuan, atau penempatan menu yang belum selesai. |
| Kaggle/Cookpad | 17 aktif / 43 diblokir | Termasuk Ayam Woku Manado, Ayam Koloke, Chicken Teriyaki, Nugget Ayam Wortel, Ayam Cabai Kawin, dan Ayam Goreng Bumbu Kuning. Langkah singkat merupakan adaptasi TAKARKUY, bukan penerbitan ulang langkah Cookpad verbatim. Bumbu campuran/SKU yang tidak dikenal, bentuk matang, serta padanan/takaran/harga yang belum lengkap tetap menghalangi resep lain. “Bumbu ayam” tidak disamakan dengan daging ayam. |
| Menu dori internal | 2 aktif dengan proksi | Gram/harga Garut dipertahankan. Gizi menggunakan **estimasi proksi patin segar GR060** (132 kkal, 17 g protein, 1,1 g karbo, 6,6 g lemak/100 g) melalui [mirror TKPI](https://alatpertanian.asia/tabel-komposisi-pangan-indonesia-tkpi-2019/), belum dicocokkan dengan PDF asli. `nutrition_verified=false`; bukan pernyataan bahwa semua dori adalah patin. |

Aturan estimasi yang dapat diperbaiki ada di `recipe_estimation.py`; angka/sumber tambahan ada di `mapping/recipe_estimation_sources.json`. Massa `oz`/`lb` mengikuti [NIST](https://www.nist.gov/pml/owm/metric-si/unit-conversion/approximate-conversions-us-customary-measures-metric), **bukan** ons Indonesia (100 g). Berat siung/cup mengacu [USDA SR Legacy](https://fdc.nal.usda.gov/download-datasets/) dan [King Arthur Ingredient Weight Chart](https://www.kingarthurbaking.com/learn/ingredient-weight-chart), dengan asumsi lokal yang dilabeli terpisah. Cup tidak disamakan dengan gram untuk semua bahan. Takaran `secukupnya` memakai asumsi **khusus bahan dan batch**, bukan angka universal. Porsi diasumsikan minimal 2, memakai pembagi internal 150 g bahan protein hewani atau 75 g beras/tepung; ini **bukan** rekomendasi kebutuhan gizi.

Harga pelengkap memakai listing penjual [UbiFresh](https://www.ubifresh.id/market/pasar-modern-bsd/), Pasar Segar, Tamarind Indonesia, Mbizmarket, Toko Kavaana, TokoWahab, e-Order Jakarta, Beorganik, Titan Baking, Bekawan dan Pasar Rakyat Bali. Gram kemasan serta setiap asumsi densitas/rendemen disimpan di JSON sumber. Referensi mentega TokoWahab adalah harga grosir dengan stok habis; listing daun salam Pasar Rakyat Bali adalah referensi historis dari situs yang menghentikan pesanan, bukan penawaran yang dijamin tersedia. Biaya menggunakan proporsi gram, belum membeli seluruh kemasan. Planner menampilkan catatan jika memakai takaran estimasi, gizi proksi, rendemen ayam utuh, atau harga pelengkap non-Garut. Harga/satuan SKU tidak boleh dianggap sama untuk semua merek.

Perbaikan aturan **v2** menaikkan jumlah siap hitung dari **93 menjadi 108 (+15)**. Singkatan satuan (`grm`, `tbs`, `cc`, `bh`, `btg`, `lmbr`) kini dikenali; judul bagian seperti “Bahan Saus” dikecualikan secara eksplisit, bukan dianggap bahan. “Garam, gula dan lada secukupnya” dipecah dan diaudit per komponen, bukan dipetakan hanya ke satu bahan. Komponen tidak dikenal tetap menghalangi resep; takaran angka bersama seperti “1 sdm garam dan gula” tidak digandakan. Saus tomat dibedakan dari tomat, minyak wijen dari minyak goreng, dan bay leaf dari daun salam Indonesia.

Ayam `1 ekor` memakai **asumsi** 1.000 g massa beli dan 60% bagian termakan (ayam “jumbo”: 1.500 g); ini bukan hasil timbang. Audit menyimpan `quantity_g` untuk gizi dan `purchase_quantity_g` untuk biaya. Planner menghitung harga dari massa beli, sehingga tulang tidak dihitung sebagai protein dan biaya tidak diperkecil memakai massa daging saja.

Tambahan gizi/proksi dicatat dengan `nutrition_verified=false`. Kaldu ayam bubuk memakai proksi USDA, **bukan label gizi Royco**; kecap manis memakai snapshot satu SKU Bango dari [Open Food Facts](https://world.openfoodfacts.org/product/8999999002503), bukan gizi semua kecap. Daun jeruk memakai label produk beku [Cock Brand/CT Food](https://ctfood.se/lime-leaf-frozen-30x114g-cock-brand/?language=en). **Daun salam segar adalah estimasi**, bukan nilai TKPI segar: makro bubuk kering NR017 dari [mirror TKPI](https://alatpertanian.asia/tabel-komposisi-pangan-indonesia-tkpi-2019/) dengan kadar air sumber 13,1% diskalakan ke **asumsi kadar air segar 70%**. Penyerapan saat daun hanya direbus lalu dibuang belum dimodelkan. Pilihan proksi ini merupakan varian resep estimasi, tidak membuat mapping merek global untuk pantry/OCR.

Penghalang 139 resep yang tersisa: **132** masih membutuhkan padanan bahan/bentuk produk, **56** takaran, **54** harga, **5** gizi, dan **1** massa beli/rendemen (minyak untuk deep-fry). Hitungan dapat tumpang tindih; penempatan waktu makan juga dapat menjadi penghalang. Rinciannya tetap di `processed/recipe_readiness.csv`.

[Ketentuan TheMealDB](https://themealdb.com/terms_of_use.php) ditinjau untuk penggunaan data dari endpoint API pada demonstrasi ini; ketentuan distribusi komersial/app store tetap perlu dipatuhi. Bahan babi, alkohol, makanan matang, bumbu campuran yang tidak terpetakan, atau bahan tidak dikenal tidak dibuang supaya angka resep terlihat lengkap. Proksi/pilihan bahan yang digunakan disebut eksplisit dalam audit. Air/alat pembungkus masak yang dikecualikan juga dicatat. Nama seperti basil ≠ kemangi dan jamur generik ≠ jamur tiram tidak disamakan begitu saja.

Empat menu buah campuran sekarang **aktif**. Gizi per orang dihitung dari gram bagian termakan pada resep internal dan data per 100 g [Bapanas](https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia) (resep dasar 2 porsi):

| Menu | Kkal | Protein | Karbohidrat | Lemak |
|---|---:|---:|---:|---:|
| Pisang dan jeruk | 165,20 | 4,28 g | 43,94 g | 0,76 g |
| Melon dan pisang | 135,41 | 2,18 g | 37,98 g | 0,07 g |
| Jeruk dan melon | 96,93 | 2,43 g | 26,12 g | 0,75 g |
| Pisang, jeruk, dan melon | 119,59 | 2,64 g | 32,53 g | 0,42 g |

Angka ini adalah estimasi dari komposisi bahan mentah, bukan nilai lab hidangan jadi. Harga buah memakai snapshot [Bapokting Kabupaten Garut](https://bapokting.disperindag.garutkab.go.id/Bapokting/) 28 September 2026 per kg: jeruk Rp20.333, pisang Rp6.588, melon Rp15.533. `mapping/fruit_purchase_units.json` memakai proksi berat dan rendemen buah utuh dari [USDA Food Buying Guide, Section 3](https://foodbuyingguide.fns.usda.gov/files/Reports/USDA_FBG_Section3_Fruits_YieldTable.pdf): pisang ±126 g/buah dan 64% termakan, jeruk ±133 g/buah dan 73% termakan, melon kecil ±850 g/buah dan 47% termakan. Ini **bukan** ukuran buah atau minimum pembelian yang terverifikasi pada toko Garut; varietas lokal dapat berbeda. Planner membulatkan kebutuhan satu rencana ke buah utuh, menghitung biaya dari perkiraan massa yang dibeli × harga Garut/kg, dan menampilkan perkiraan sisa bagian termakan. Biaya per-menu dipakai sebagai batas konservatif selama pencarian; biaya akhir dihitung ulang setelah kebutuhan semua hari digabung. Karena pencarian awal konservatif, rencana hemat tertentu masih mungkin tidak terpilih pada budget sangat ketat.

Estimasi ini dibuat setelah pengguna menyetujui perkiraan untuk takaran/porsi yang tidak pasti. Menemukan gizi makanan *bernama sama* tetap tidak membuktikan komposisinya identik. Karena itu versi aturan, proksi, sumber, dan status estimasi disimpan; resep hanya siap dihitung jika setiap bahan termakan mempunyai gram, empat makro, dan harga yang dapat dipakai. **Angka gizi yang tidak diketahui tidak diisi nol.** Untuk menaikkan 139 resep berikutnya, lengkapi penghalang di `recipe_readiness.csv`, bukan sekadar mengubah `is_plannable`.

## Dataset kandidat yang dikumpulkan

| Dataset | Baris | Isi, asal, dan status |
|---|---:|---|
| `staging/openfoodfacts_products.csv` | 231 produk unik | Nama, barcode, merek, ukuran, kategori, dan makro per 100 g bila tersedia. **130** memiliki keempat makro; **217** bernama. Sampel dari [Open Food Facts API](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/) pada 1 Oktober 2026: dua halaman populer bertag Indonesia + satu halaman merek Indomie. Konten pengguna bisa salah/tidak lengkap; lisensi database ODbL dan atribusi perlu dipatuhi. Tidak mewakili seluruh Superindo/Indomaret. |
| `staging/product_ingredient_candidates.csv` | 38 usulan | Usulan produk bernama mi/noodle → konsep `ING-MIE-INSTAN` berdasar kata pada nama saja. **Belum disetujui**, bukan bukti merek benar, kandungan gizi sama, isi kemasan sama, atau semua produk mi cocok untuk resep tertentu. |
| `staging/recipe_candidates.csv` | 1.500 kandidat | 1.400 resep Indonesia dari [Purwanto dkk., Mendeley Data v3](https://data.mendeley.com/datasets/8b4ztns76h/3) (CC BY 4.0; langkah, bahan, porsi, makro terlapor) dan 100 kandidat internasional dari [TheMealDB](https://www.themealdb.com/docs_api_guide.php). Belum siap planner; hak penggunaan konten resep, satuan, porsi, mapping bahan, gizi, harga, dan keamanan harus diperiksa. TheMealDB hanya diindeks sebagai metadata pada CSV ini; detail mentahnya ada di `scratch/`. |
| `staging/mendeley_unmatched_ingredients.csv` | 1.716 istilah | Istilah bahan yang oleh dataset Mendeley dilaporkan belum terpetakan, total 5.898 kemunculan. Ini **istilah mentah**, bukan 1.716 bahan makanan baru: termasuk `air`, `garam`, sinonim, bumbu campuran, dan kata bising. Perlu deduplikasi dan verifikasi nutrisi. |
| `staging/themealdb_breakfast_review.csv` | 189 baris review | Antrean lama 26 kandidat sarapan/pisang dari TheMealDB; jangan digabung begitu saja dengan 100 kandidat baru karena mungkin tumpang tindih. |

Sumber asli berada di `raw/openfoodfacts_indonesia_sample.json`, `scratch/mendeley_indonesian_recipe_nutrition_v3.json`, dan `scratch/themealdb_100_candidates.json`. Snapshot Open Food Facts mencakup 231 barcode berbeda dari 238 hasil halaman sebelum deduplikasi. Banyak resep Mendeley memiliki variasi nama/duplikasi; **1.400 baris bukan 1.400 hidangan unik**. Gizi Mendeley dilaporkan oleh penyusun dataset dan sebagian konversi satuan menggunakan LLM; jangan menganggap angka itu terverifikasi untuk target diet pengguna.

## Sumber mentah lain yang tersedia

- `raw/tkpi_2020.pdf`: [TKPI Kemenkes](https://repository.kemkes.go.id/book/668), masih berupa pindai dan **belum** diekstrak ke katalog.
- `raw/usda_sr_legacy_2018-04.zip`: [USDA SR Legacy](https://fdc.nal.usda.gov/download-datasets/), fallback komposisi pangan luar negeri; padanan ke bahan Indonesia perlu tinjauan. [USDA menyatakan data FoodData Central CC0](https://fdc.nal.usda.gov/api-guide/).
- `raw/foodkeeper_mirror_2019.csv`: mirror historis rujukan [FoodKeeper](https://catalog.data.gov/dataset/fsis-foodkeeper-data); perlu cocokkan ulang dengan sumber resmi saat bisa diakses.
- `raw/bapanas_fresh_nutrition.html`, `raw/garut_prices_2026-09-28.html`, `raw/pihps_prices_2026-09-28.json`: snapshot yang mendasari tabel aktif.
- `raw/indonesian_food_recipes.zip`: arsip Kaggle lama; bahan dipakai untuk audit/estimasi. Resep tambahan yang aktif menggunakan langkah adaptasi TAKARKUY.
- `raw/themealdb_breakfast_snapshot.json`: snapshot kandidat sarapan yang terpisah dari kumpulan 100 resep.

## Gap sebelum fitur yang diinginkan siap penuh

### Perkiraan masa simpan pada pantry

Input manual dan OCR memakai suhu ruang jika lokasi tidak dipilih. Backend mencocokkan nama ke katalog lokal (tanpa panggilan Gemini tambahan saat menyimpan), menyimpan referensi bahan dan tanggal awal, lalu memakai batas minimum acuan lokasi yang sesuai. Pilihan lokasi hanya **Kulkas, Freezer, dan Suhu Ruang**: kulkas (`chiller`) dipetakan ke `kulkas`, freezer ke `freezer`, dan suhu ruang memakai acuan `suhu_ruang`. Tanggal kosong jika acuan lokasi tidak ada; tempe pada snapshot ini hanya punya acuan kulkas/freezer, bukan suhu ruang. Tidak ada durasi baru yang dikarang untuk mengisi gap itu.

Saat lokasi diganti, perkiraan langsung diperbarui di tabel dan disimpan lewat tombol **Simpan**. Hitungan tetap memakai tanggal belanja atau tanggal ditambahkan, sehingga pergantian lokasi tidak mereset usia bahan. Tanggal label kemasan dapat diisi manual. Ini estimasi, bukan jaminan keamanan dan bukan bukti bahan yang sudah rusak dapat dipulihkan dengan pendinginan. Default suhu ruang hanya perilaku input, bukan rekomendasi penyimpanan bahan mudah rusak; lihat [panduan FoodSafety.gov](https://www.foodsafety.gov/keep-food-safe/4-steps-to-food-safety).

Migrasi `pantry.0006_pantryitem_ingredient_pantryitem_starting_on_and_more` menambahkan referensi bahan dan tanggal awal tanpa menghapus stok lama. Pada stok lama, pencocokan/tanggal awal dipulihkan saat pengguna menyimpan perubahan; membuka halaman tidak mengubah data.

Migrasi `pantry.0007_simplify_storage_locations` mengganti lokasi lama `lemari_kering` menjadi `suhu_ruang`, tanpa menghapus stok atau mengubah tanggal yang sudah tersimpan. Nama tampilan `chiller` disederhanakan menjadi **Kulkas**; ID lokasi kulkas tetap sama.

Verifikasi setelah perubahan ini: **118 tes Django dan 12 tes JavaScript** lolos, termasuk default manual/OCR, pergantian lokasi, acuan yang kosong, tanggal belanja lama, override tanggal manual, isolasi sesi, serta penyederhanaan lokasi dan tabel. Migrasi diterapkan lokal; deployment PWS belum diverifikasi. Tabel menyembunyikan kolom Sumber tetapi data asal stok tetap disimpan; informasi masa simpan tampil kecil di bawah input tanggal.

### Pekerjaan lanjutan

1. **Bahan dan produk.** Belum ada master nasional seluruh bahan/varian pasar. Contoh `Mie Instan` sudah ada tetapi gizinya kosong; `Kerang` dan `Pasta` belum menjadi bahan aktif. Barcode produk tidak boleh otomatis disamakan dengan bahan generik: `Indomie` dapat menjadi kandidat stok mi instan, tetapi bumbu, bobot bersih, dan gizi produk harus tetap spesifik per SKU. Perlu tabel produk ↔ bahan yang direview dan konversi berat kemasan sebelum planner memakai stoknya.
2. **Resep.** Resep kerang, burger, dan spaghetti tersedia sebagai kandidat, tetapi belum punya relasi bahan, satuan gram, harga, dan gizi yang lolos validasi planner. Kurasi bertahap berdasarkan bahan yang sering muncul lebih aman daripada memasukkan semua 1.500 resep sekaligus.
3. **Penyimpanan.** Lama simpan bergantung pada bentuk bahan, kondisi awal, kemasan, suhu, dan tanggal label. FoodKeeper dapat memberi saran awal, bukan memutuskan makanan aman atau tanggal kedaluwarsa pasti. Bahan/produk yang belum terpetakan tetap perlu input atau persetujuan pengguna.
4. **OCR dan pembelajaran.** Koreksi pengguna dapat menjadi kandidat alias; baris yang sama dari banyak pengguna dan pemeriksaan manusia dapat memperkaya katalog. Jangan otomatis menganggap keluaran OCR/LLM atau satu koreksi sebagai fakta global. Perlu rekam sumber, status review, versi, dan kemampuan membatalkan mapping yang salah. Untuk ekor panjang produk baru, fallback Gemini mungkin makin jarang tetapi tidak realistis dijamin hilang seluruhnya.
5. **Hak pakai.** ODbL Open Food Facts punya kewajiban atribusi/share-alike sesuai penggunaan; TheMealDB punya batasan penggunaan API. Tinjau sebelum menyebarkan ulang dataset atau mengaktifkan konten resep pihak ketiga.

## Memperbarui dan memeriksa

Dari akar proyek:

```bash
python3 data/fetch_openfoodfacts_products.py --pages 2 --page-size 100 --brand indomie
python3 data/build_candidate_indexes.py
python3 data/build_final.py
python3 data/validate_candidates.py
python3 data/validate_catalog.py
python manage.py import_catalog data/fixtures/catalog_seed.json --sync-generated-relations
```

Opsi impor terakhir menyinkronkan relasi bahan/tag **buatan generator** pada resep yang tercantum dalam fixture; relasi bersumber pengguna, resep lain, stok dan riwayat rencana tidak dihapus. Jangan memakai opsi ini pada fixture parsial untuk resep yang ingin mempertahankan relasi generator lama.

Perintah pertama mengakses internet dan mengganti snapshot kandidat Open Food Facts; jangan menjalankannya otomatis pada setiap request aplikasi. Open Food Facts meminta unduhan [bulk export](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/) bila membutuhkan lebih dari beberapa ratus produk, bukan memperbanyak panggilan search API. Perintah kedua membangun ulang indeks dari snapshot lokal. Keduanya **tidak** mengubah fixture Django atau mempromosikan kandidat menjadi data aktif.

## Audit dan cleanup — 1 Oktober 2026

- **Katalog tetap 108 resep siap hitung, 187 bahan, dan 143 baris harga.** Tidak ditemukan PK ganda atau relasi bahan-resep/tag/konversi yang berulang dengan ID berbeda. Varian resep, SKU, harga berbeda wilayah, dan catatan berbeda kondisi simpan tidak dihapus hanya karena namanya mirip.
- Delapan CSV utama, audit estimasi, indeks kandidat, dan kedua fixture lolos validasi. Build ulang sesudah perapian kode menghasilkan byte yang sama untuk tabel/fixture yang dihasilkan. Ukuran dan SHA-256 seluruh sumber yang tercatat dalam `raw/manifest.json` cocok.
- `data/fixtures/catalog_seed.json` dan `apps/catalog/fixtures/catalog_seed.json` sengaja tetap ada: satu untuk pipeline data/impor eksplisit, satu untuk fixture Django dan tes. Generator menulis keduanya dari keluaran yang sama. Arsip mentah serta antrean `scratch/` dan `staging/` masih diperlukan untuk membangun ulang/kurasi; bukan junk yang aman dihapus.
- Metadata macOS `.DS_Store` dikeluarkan dari proyek dan diabaikan Git. Kode Python dirapikan dengan aturan di `ruff.toml`; helper kandidat TheMealDB yang tidak digunakan dihapus. Ekspor CSV TheMealDB diperbaiki agar field detail JSON tidak membuat ekspor gagal, dan pemilihan lintas kategori kini menolak ID resep berulang.
- Catatan `Ingredient.calories_method` kini `TextField` melalui migrasi `catalog.0002_ingredient_calories_method_text`. Sebelumnya satu catatan estimasi memiliki 328 karakter: SQLite menerima, tetapi `varchar(255)` PostgreSQL tidak. Catatan sumber tidak dipotong. Importer menolak field tak dikenal/terlalu panjang sebelum menulis, merangkum duplikat identik, menolak ID konflik, dan menjaga tag bersumber pengguna saat promosi/sinkronisasi.
- Transport Gemini untuk OCR foto dan pencocokan nama disatukan di `apps/pantry/gemini.py`. Keduanya memakai default `gemini-2.5-flash-lite`, key hanya pada header server, timeout terbatas, serta kegagalan respons/JSON yang ditangani tanpa membocorkan isi respons. Tes Gemini memakai respons buatan, bukan API berbayar/live.
- Verifikasi: **106 tes Django**, **9 tes parser JavaScript**, pemeriksaan sintaks JavaScript, lint/format Python, `makemigrations --check --dry-run`, validasi katalog/kandidat, dan `collectstatic --noinput` berhasil. Migrasi baru diterapkan pada database lokal tanpa menghapus data pengguna. Tidak ada commit/push/deploy dalam audit ini.

**Batas audit:** belum memverifikasi deployment PWS, koneksi PostgreSQL produksi, kuota/key Gemini nyata, atau akurasi Tesseract pada foto baru di browser. `check --deploy` dalam konfigurasi produksi menemukan dua peringatan: HSTS dan pengalihan HTTPS belum diatur oleh Django. Pastikan kebijakan reverse proxy PWS sebelum mengaktifkannya agar tidak menimbulkan loop redirect. Sebelum mengimpor fixture baru di PWS, jalankan `python manage.py migrate --noinput`.

Perilaku aplikasi yang belum diubah: stok pantry dan koreksi pribadi masih **berbasis sesi browser**, bukan kepemilikan akun lintas perangkat. Batas Gemini adalah per sesi/hari, bukan kuota akun/IP atau pembatas global biaya. Pendaftaran masih menyimpan email sebagai username otomatis; kolom username pilihan pengguna belum diimplementasikan. Hal-hal ini adalah batas fitur saat ini, bukan dianggap sudah selesai hanya karena tes lolos.
