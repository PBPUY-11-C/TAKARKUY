# Inventaris dataset TAKARKUY

Inventaris diperbarui pada **8 Oktober 2026**. Harga Garut tetap snapshot 28 September; tanggal review bukan tanggal publikasi harga. Angka menunjukkan baris data, bukan jumlah makanan unik. Ada tiga tingkat: **aktif** (`processed/` dan `mapping/`, dipakai aplikasi), **kandidat** (`staging/` dan `scratch/`, kurasi), dan **sumber mentah** (`raw/`, jejak asal/rekonstruksi). Sebagian kandidat sudah dipromosikan; jangan menjumlahkan staging dengan aktif. Tidak ada klaim cakupan seluruh bahan Indonesia/produk minimarket.

## Dataset aktif

| Dataset | Baris | Fungsi dan batasnya |
|---|---:|---|
| `processed/ingredients.csv` | 201 | Nama/ID bahan; **163** memiliki empat makro. Sumber [Bapanas](https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia), [USDA](https://fdc.nal.usda.gov/download-datasets/), TKPI melalui mirror/Mendeley, label produk, serta satu produk Open Food Facts; semuanya dengan sumber/status. Proksi bukan nilai terverifikasi. |
| `processed/ingredient_allergens.csv` | 201 | Input kurasi `mapping/ingredient_allergens.csv`; 167 review jenis bahan tunggal dan 34 unknown. 9 kelompok berdasarkan [FSA](https://www.food.gov.uk/business-guidance/allergen-guidance-for-food-businesses), bukan sertifikasi atau verifikasi label merek. Build menggabungkan metadata ke master bahan/fixture tanpa menambah objek. |
| `processed/ingredient_prices.csv` | 163 | 78 Garut + 21 PIHPS (28 September 2026), ditambah **64 referensi toko daring non-Garut** (44 dari kurasi 1 Oktober dan 20 dari kurasi 5 Oktober). Tanggal terbit listing tidak diketahui; bukan harga real-time. Harga Garut tetap diutamakan. |
| `processed/ingredient_shelf_life.csv` | 149 | Rentang lama simpan untuk 80 bahan/berbagai kondisi. Berbasis [USDA FoodKeeper](https://catalog.data.gov/dataset/fsis-foodkeeper-data) melalui mirror historis; semua perlu verifikasi lokal. **Bukan** tanggal kedaluwarsa pada kemasan. |
| `processed/recipes.csv` | 438 | **300 siap dihitung**: 87 internal, 18 adaptasi Kaggle, 4 TheMealDB, 191 Mendeley; 6 di antaranya `is_active=false` (duplikat/data sumber janggal), sehingga **294 tampil** di aplikasi. **138** diblokir. Siap dihitung bukan izin publikasi: teks langkah Mendeley ditahan. |
| `processed/recipe_ingredients.csv` | 3.027 | Hubungan bahan dan gram; takaran tambahan memakai `quantity_status=estimated` beserta audit di `raw_text`. Bahan berulang dalam resep dijumlahkan menjadi satu relasi/ID. |
| `processed/recipe_tags.csv` | 2.174 | Tag resep; label diet/halal bukan sertifikasi. Tag kandidat dibersihkan saat promosi. |
| `mapping/ingredient_aliases.csv` | 376 | Padanan nama bahan/alias; ID lama dipertahankan agar relasi stok tidak putus. |
| `mapping/unit_conversions.csv` | 612 | Massa standar dan konversi spesifik. Asumsi takaran resep **tidak** menjadi konversi kemasan global untuk OCR/pantry. |
| `staging/recipe_quantity_estimates.csv` | 1.824 | Audit **semua bahan dari 160 kandidat**, termasuk 38 komponen tambahan hasil pemisahan bahan gabungan: nama/takaran asli, gram termakan dan massa beli jika dapat dihitung, padanan bahan, asumsi, sumber, dan penghalang. Baris `blocked` dapat memiliki gram yang diketahui tetapi belum punya padanan gizi/harga. |
| `processed/recipe_readiness.csv` | 438 | Status/penyebab per resep; memudahkan memilih penghalang yang perlu dilengkapi. |
| `processed/recipe_estimated_nutrition.csv` | 300 | Hasil perhitungan empat makro dan biaya per porsi resep siap hitung; bukan hasil uji laboratorium. |

Fixture tunggal `fixtures/catalog_seed.json` berisi **7.140 objek**. Delapan tabel utama dan fixture lolos pemeriksaan PK/FK tanpa ID ganda. Kandidat yang dipromosikan **mengganti metadata dengan ID sama**, bukan ditambahkan lagi. Duplikat identik diringkas; ID sama dengan isi berbeda ditolak, bukan diam-diam ditimpa. Kurasi nama mengeluarkan 48 resep dari hasil ekspansi sebelumnya: duplikat hidangan dan menu di luar cakupan, dengan alasan eksplisit dalam `mapping/recipe_name_overrides.csv`; sumber mentah tetap disimpan. Build/validator menolak nama resep aktif ganda. `validate_docs.py` membandingkan hitungan ketiga dokumen dengan keluaran build agar angka tidak tertinggal.

### Estimasi dan resep yang masih diblokir

| Kelompok | Jumlah | Penghalang utama |
|---|---:|---|
| TheMealDB | 4 aktif / 96 diblokir | Aktif: Bread Omelette, Algerian Kefta, Fasoliyyeh, Algerian Flafla. Semua porsi/takaran rumah tangga diberi label estimasi. Sisanya masih memiliki padanan bahan/bentuk produk, harga, satuan, atau penempatan menu yang belum selesai. |
| Kaggle/Cookpad | 18 aktif / 42 diblokir | Langkah singkat merupakan adaptasi TAKARKUY, bukan penerbitan ulang langkah Cookpad verbatim. Bumbu campuran/SKU, bentuk matang, serta padanan/takaran/harga belum lengkap tetap menghalangi resep lain. “Bumbu ayam” tidak disamakan dengan daging ayam. |
| Mendeley | 191 siap hitung (186 aktif) untuk simulasi | Bahan, porsi dan empat makro dipadankan/dihitung ulang; takaran dan slot diberi status estimasi. Teks langkah tidak dipublikasikan sampai review sumber selesai. |
| Menu dori internal | 2 aktif dengan proksi | Gram/harga Garut dipertahankan. Gizi menggunakan **estimasi proksi patin segar GR060** (132 kkal, 17 g protein, 1,1 g karbo, 6,6 g lemak/100 g) melalui [mirror TKPI](https://alatpertanian.asia/tabel-komposisi-pangan-indonesia-tkpi-2019/), belum dicocokkan dengan PDF asli. `nutrition_verified=false`; bukan pernyataan bahwa semua dori adalah patin. |

Aturan estimasi yang dapat diperbaiki ada di `recipe_estimation.py`; angka/sumber tambahan ada di `mapping/recipe_estimation_sources.json`. Massa `oz`/`lb` mengikuti [NIST](https://www.nist.gov/pml/owm/metric-si/unit-conversion/approximate-conversions-us-customary-measures-metric), **bukan** ons Indonesia (100 g). Berat siung/cup mengacu [USDA SR Legacy](https://fdc.nal.usda.gov/download-datasets/) dan [King Arthur Ingredient Weight Chart](https://www.kingarthurbaking.com/learn/ingredient-weight-chart), dengan asumsi lokal yang dilabeli terpisah. Cup tidak disamakan dengan gram untuk semua bahan. Takaran `secukupnya` memakai asumsi **khusus bahan dan batch**, bukan angka universal. Porsi diasumsikan minimal 2, memakai pembagi internal 150 g bahan protein hewani atau 75 g beras/tepung; ini **bukan** rekomendasi kebutuhan gizi.

Harga pelengkap memakai listing penjual [UbiFresh](https://www.ubifresh.id/market/pasar-modern-bsd/), Pasar Segar, Tamarind Indonesia, Mbizmarket, Toko Kavaana, TokoWahab, e-Order Jakarta, Beorganik, Titan Baking, Bekawan dan Pasar Rakyat Bali. Gram kemasan serta setiap asumsi densitas/rendemen disimpan di JSON sumber. Referensi mentega TokoWahab adalah harga grosir dengan stok habis; listing daun salam Pasar Rakyat Bali adalah referensi historis dari situs yang menghentikan pesanan, bukan penawaran yang dijamin tersedia. Biaya menggunakan proporsi gram, belum membeli seluruh kemasan. Planner menampilkan catatan jika memakai takaran estimasi, gizi proksi, rendemen ayam utuh, atau harga pelengkap non-Garut. Harga/satuan SKU tidak boleh dianggap sama untuk semua merek.

Perbaikan aturan **v2** menaikkan jumlah siap hitung dari **93 menjadi 108 (+15)**. Singkatan satuan (`grm`, `tbs`, `cc`, `bh`, `btg`, `lmbr`) kini dikenali; judul bagian seperti “Bahan Saus” dikecualikan secara eksplisit, bukan dianggap bahan. “Garam, gula dan lada secukupnya” dipecah dan diaudit per komponen, bukan dipetakan hanya ke satu bahan. Komponen tidak dikenal tetap menghalangi resep; takaran angka bersama seperti “1 sdm garam dan gula” tidak digandakan. Saus tomat dibedakan dari tomat, minyak wijen dari minyak goreng, dan bay leaf dari daun salam Indonesia.

Ayam `1 ekor` memakai **asumsi** 1.000 g massa beli dan 60% bagian termakan (ayam “jumbo”: 1.500 g); ini bukan hasil timbang. Audit menyimpan `quantity_g` untuk gizi dan `purchase_quantity_g` untuk biaya. Planner menghitung harga dari massa beli, sehingga tulang tidak dihitung sebagai protein dan biaya tidak diperkecil memakai massa daging saja.

Tambahan gizi/proksi dicatat dengan `nutrition_verified=false`. Kaldu ayam bubuk memakai proksi USDA, **bukan label gizi Royco**; kecap manis memakai snapshot satu SKU Bango dari [Open Food Facts](https://world.openfoodfacts.org/product/8999999002503), bukan gizi semua kecap. Daun jeruk memakai label produk beku [Cock Brand/CT Food](https://ctfood.se/lime-leaf-frozen-30x114g-cock-brand/?language=en). **Daun salam segar adalah estimasi**, bukan nilai TKPI segar: makro bubuk kering NR017 dari [mirror TKPI](https://alatpertanian.asia/tabel-komposisi-pangan-indonesia-tkpi-2019/) dengan kadar air sumber 13,1% diskalakan ke **asumsi kadar air segar 70%**. Penyerapan saat daun hanya direbus lalu dibuang belum dimodelkan. Pilihan proksi ini merupakan varian resep estimasi, tidak membuat mapping merek global untuk pantry/OCR.

Saat ini 138 resep masih diblokir (96 TheMealDB, 42 Kaggle). Penghalang dapat tumpang tindih: padanan bahan/bentuk produk, takaran, harga, gizi, massa beli/rendemen, atau slot makan. Rincian terbaru ada di `processed/recipe_readiness.csv`; alasan penolakan kandidat Mendeley ada di `staging/mendeley_recipe_audit.csv` dan tidak semuanya dimasukkan katalog aktif.

[Ketentuan TheMealDB](https://themealdb.com/terms_of_use.php) ditinjau untuk penggunaan data dari endpoint API pada demonstrasi ini; ketentuan distribusi komersial/app store tetap perlu dipatuhi. Bahan babi, alkohol, makanan matang, bumbu campuran yang tidak terpetakan, atau bahan tidak dikenal tidak dibuang supaya angka resep terlihat lengkap. Proksi/pilihan bahan yang digunakan disebut eksplisit dalam audit. Air/alat pembungkus masak yang dikecualikan juga dicatat. Nama seperti basil ≠ kemangi dan jamur generik ≠ jamur tiram tidak disamakan begitu saja.

Empat menu buah campuran sekarang **aktif**. Gizi per orang dihitung dari gram bagian termakan pada resep internal dan data per 100 g [Bapanas](https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia) (resep dasar 2 porsi):

| Menu | Kkal | Protein | Karbohidrat | Lemak |
|---|---:|---:|---:|---:|
| Pisang dan jeruk | 165,20 | 4,28 g | 43,94 g | 0,76 g |
| Melon dan pisang | 135,41 | 2,18 g | 37,98 g | 0,07 g |
| Jeruk dan melon | 96,93 | 2,43 g | 26,12 g | 0,75 g |
| Pisang, jeruk, dan melon | 119,59 | 2,64 g | 32,53 g | 0,42 g |

Angka ini adalah estimasi dari komposisi bahan mentah, bukan nilai lab hidangan jadi. Harga buah memakai snapshot [Bapokting Kabupaten Garut](https://bapokting.disperindag.garutkab.go.id/Bapokting/) 28 September 2026 per kg: jeruk Rp20.333, pisang Rp6.588, melon Rp15.533. `mapping/fruit_purchase_units.json` memakai proksi berat dan rendemen buah utuh dari [USDA Food Buying Guide, Section 3](https://foodbuyingguide.fns.usda.gov/files/Reports/USDA_FBG_Section3_Fruits_YieldTable.pdf): pisang ±126 g/buah dan 64% termakan, jeruk ±133 g/buah dan 73% termakan, melon kecil ±850 g/buah dan 47% termakan. Ini **bukan** ukuran buah atau minimum pembelian yang terverifikasi pada toko Garut; varietas lokal dapat berbeda. Planner membulatkan kebutuhan satu rencana ke buah utuh, menghitung biaya dari perkiraan massa yang dibeli × harga Garut/kg, dan menampilkan perkiraan sisa bagian termakan. Biaya per-menu dipakai sebagai batas konservatif selama pencarian; biaya akhir dihitung ulang setelah kebutuhan semua hari digabung. Karena pencarian awal konservatif, rencana hemat tertentu masih mungkin tidak terpilih pada budget sangat ketat.

Estimasi dibuat setelah pengguna menyetujui perkiraan takaran/porsi. Gizi makanan *bernama sama* tidak membuktikan komposisinya identik. Versi aturan, proksi, sumber, dan status estimasi disimpan; bahan yang dihitung memerlukan gram, empat makro, dan harga. **Angka gizi yang tidak diketahui tidak diisi nol.** Bumbu minor yang sengaja dikecualikan dari hitungan Mendeley dicatat terpisah dan ditandai; estimasi bukan perhitungan seluruh komponen terukur. Untuk menaikkan 138 resep berikutnya, lengkapi penghalang di `recipe_readiness.csv`, bukan sekadar mengubah `is_plannable`.

### Sumber tambahan dan keputusan publikasi — 5 Oktober 2026

- **Resep/gizi:** [Purwanto, Wibawa & Devi, Mendeley Data v3](https://data.mendeley.com/datasets/8b4ztns76h/3), DOI `10.17632/8b4ztns76h.3`, diterbitkan 11 Mei 2026, berlisensi [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 187 resep tambahan berasal dari sini; kenaikan total 108 → 296 juga mencakup satu kandidat Kaggle yang kini lolos. Sumber memakai TKPI serta sebagian konversi LLM, bukan pengukuran laboratorium hidangan. Gizi bahan tambahan belum dicocokkan PDF TKPI asli; proksi tetap diberi label.
- **Harga:** 20 listing tambahan dari [Sayurbox](https://www.sayurbox.com/p/labu-siam-ggdkmboo) dan [Tokopedia](https://www.tokopedia.com/kiossayurmakhaji/kelapa-parut-segar-250-gram), total 64 referensi retail non-Garut. URL per bahan, kemasan, harga dan tanggal tinjauan dicatat di `mapping/mendeley_sources.json`. Akses ulang beberapa listing dibatasi; tidak semua harga diverifikasi ulang secara independen. Harga referensi tidak mengganti snapshot Garut dan belum mencakup ongkir/pembelian kemasan utuh.
- **Audit:** `mendeley_recipes.py`, `mapping/mendeley_terms.csv`, `mapping/mendeley_sources.json`, dan `staging/mendeley_recipe_audit.csv` menyimpan mapping, versi aturan, porsi, massa termakan/beli, bumbu minor, serta alasan blocked/excluded.
- **Publikasi:** lisensi dataset dicatat, tetapi asal/izin teks langkah belum dipastikan. Teks asli dipertahankan di snapshot mentah, bukan fixture atau UI. Metadata `instructions_status=withheld_pending_rights_review` membedakan siap simulasi dan belum siap panduan memasak. Guard runtime juga berlaku untuk snapshot rencana lama. Atribusi dan perubahan ditampilkan; proses pembukaan kembali harus melalui review, bukan menyalakan env. Kriteria/keputusan rinci ada di [SOURCE_REVIEW.md](SOURCE_REVIEW.md).

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

## Perbaikan takaran dan nama resep — 8 Oktober 2026

- **Berat sumber Mendeley diperiksa.** Kolom berat dataset Mendeley sering tidak sesuai takarannya (mis. "6 butir" telur tertulis 50 g, "5 butir" kemiri 500 g, "1 sdt" gula 0,05 g). Berat sumber kini hanya dipakai bila berada pada 0,5–2× takaran rumah tangga yang sama; di luar itu dipakai estimasi TAKARKUY dan alasannya dicatat di `raw_text`/audit (aturan `takarkuy-mendeley-2026-10-08-v3`). Satuan `ekor` tidak diperiksa karena sumber juga memakainya untuk potongan.
- **Satuan Indonesia:** `lb`/`lbr` dibaca *lembar*, bukan pound (daun jeruk 1.360 g → 1,5 g). Kaldu bertakaran volume (`kaldu sapi 500 ml`) dihitung sebagai air, bukan kaldu bubuk. Minyak goreng dibatasi **15 g/porsi** sebagai bagian terserap; sisa minyak penggorengan tidak dihitung.
- **Nama dan duplikat** diatur di `mapping/recipe_name_overrides.csv`. Nilai baru `nonaktif` menulis `is_active=false` tanpa menghapus baris/kode, sehingga rencana tersimpan tetap terbaca; `exclude` tetap hanya untuk Mendeley. Ganti nama tidak lagi membebaskan judul sumber untuk duplikatnya. Resep internal memakai nama sesuai cara masak, mis. "Nasi + Ikan Kembung Masak Cabai".
- Dampak dibanding katalog sebelumnya: 8 resep dikeluarkan dari fixture, 6 resep dinonaktifkan, dan 12 resep Mendeley baru lolos validasi. Total resep aktif siap dihitung berubah dari 296 menjadi 294. Sarapan aktif 35.

## Cleanup fixture — 5 Oktober 2026

- Fixture katalog kini hanya `data/fixtures/catalog_seed.json`. Salinan identik aplikasi dihapus; impor eksplisit, `loaddata catalog_seed.json`, dan tes memakai file yang sama melalui `FIXTURE_DIRS`.
- Generator tidak lagi menulis salinan aplikasi. Validator serta `FixtureDiscoveryTests` mencegah regresi pemuatan/salinan fixture. Referensi perintah impor pada README dan panduan akun disamakan.
- Build ulang mempertahankan byte seluruh 17 file fixture/processed/staging yang diperiksa; 7.048 objek, 434 resep dan 296 siap dihitung tidak berubah. Delapan snapshot pada manifest raw tetap cocok ukuran dan SHA-256. Pengurangan sekitar 4,3 MiB adalah penghapusan salinan file, bukan penghapusan resep atau database pengguna.
- `raw/`, `scratch/`, `mapping/`, `processed/`, dan `staging/` dipertahankan untuk reproduksi, kurasi dan audit. File `__init__.py` kosong adalah struktur paket, bukan junk. `.env`, database lokal, virtualenv, cache dan hasil collectstatic tetap diabaikan Git. Tidak ada sumber maupun data pengguna yang dihapus.

## Audit dan cleanup — 1 Oktober 2026 (historis)

- **Catatan historis 1 Oktober: 108 resep siap hitung, 187 bahan, dan 143 baris harga** (bukan inventaris saat ini; angka terbaru ada di tabel atas). Tidak ditemukan PK ganda atau relasi bahan-resep/tag/konversi berulang. Varian resep, SKU, harga wilayah berbeda, dan kondisi simpan tidak dihapus hanya karena namanya mirip.
- Delapan CSV utama, audit estimasi, indeks kandidat, dan kedua fixture lolos validasi. Build ulang sesudah perapian kode menghasilkan byte yang sama untuk tabel/fixture yang dihasilkan. Ukuran dan SHA-256 seluruh sumber yang tercatat dalam `raw/manifest.json` cocok.
- Pada audit historis ini terdapat dua salinan fixture. Cleanup 5 Oktober menggantinya dengan satu `data/fixtures/catalog_seed.json`: Django memakai `FIXTURE_DIRS`, generator hanya menulis satu file, dan validator mencegah salinan app muncul lagi. Arsip mentah serta antrean `scratch/` dan `staging/` masih diperlukan untuk membangun ulang/kurasi; bukan junk yang aman dihapus.
- Metadata macOS `.DS_Store` dikeluarkan dari proyek dan diabaikan Git. Kode Python dirapikan dengan aturan di `ruff.toml`; helper kandidat TheMealDB yang tidak digunakan dihapus. Ekspor CSV TheMealDB diperbaiki agar field detail JSON tidak membuat ekspor gagal, dan pemilihan lintas kategori kini menolak ID resep berulang.
- Catatan `Ingredient.calories_method` kini `TextField` melalui migrasi `catalog.0002_ingredient_calories_method_text`. Sebelumnya satu catatan estimasi memiliki 328 karakter: SQLite menerima, tetapi `varchar(255)` PostgreSQL tidak. Catatan sumber tidak dipotong. Importer menolak field tak dikenal/terlalu panjang sebelum menulis, merangkum duplikat identik, menolak ID konflik, dan menjaga tag bersumber pengguna saat promosi/sinkronisasi.
- Transport Gemini untuk OCR foto dan pencocokan nama disatukan di `apps/pantry/gemini.py`. Keduanya memakai default `gemini-2.5-flash-lite`, key hanya pada header server, timeout terbatas, serta kegagalan respons/JSON yang ditangani tanpa membocorkan isi respons. Tes Gemini memakai respons buatan, bukan API berbayar/live.
- Verifikasi: **106 tes Django**, **9 tes parser JavaScript**, pemeriksaan sintaks JavaScript, lint/format Python, `makemigrations --check --dry-run`, validasi katalog/kandidat, dan `collectstatic --noinput` berhasil. Migrasi baru diterapkan pada database lokal tanpa menghapus data pengguna. Tidak ada commit/push/deploy dalam audit ini.

**Batas audit:** belum memverifikasi deployment PWS, koneksi PostgreSQL produksi, kuota/key Gemini nyata, atau akurasi Tesseract pada foto baru di browser. `check --deploy` dalam konfigurasi produksi menemukan dua peringatan: HSTS dan pengalihan HTTPS belum diatur oleh Django. Pastikan kebijakan reverse proxy PWS sebelum mengaktifkannya agar tidak menimbulkan loop redirect. Sebelum mengimpor fixture baru di PWS, jalankan `python manage.py migrate --noinput`.

### Otorisasi dan kepemilikan akun — 1 Oktober 2026

Stok pantry dan koreksi pribadi sekarang milik akun melalui FK `user`, sehingga dapat diakses lintas perangkat oleh akun yang sama. Halaman Modul 2/4/5 dan seluruh API pantry wajib login; setiap baca/ubah/hapus stok difilter berdasarkan pemilik. Koreksi bersama menghitung minimal 5 akun berbeda yang sepakat, bukan sesi browser. Modul 1 tetap terbuka untuk guest dengan batas **3 rencana berhasil per 24 jam per browser**, memakai cookie ID bertanda tangan dan counter database atomik. Hasil terakhir tetap tersedia di sesi; invalid input/error/budget tidak cukup tidak mengurangi kuota.

Migrasi baru: `budget_planner.0001_initial` dan `pantry.0008_pantryitem_user_pantrynamecorrection_user_and_more`. Stok/koreksi lama tetap disimpan dengan pemilik kosong; tidak otomatis diberikan ke akun yang login, tidak terlihat dalam pantry akun, dan tidak dihitung sebagai suara komunitas. Pemiliknya perlu diverifikasi sebelum penetapan manual. Dataset katalog tidak berubah.

Verifikasi: **143 tes Django dan 12 tes JavaScript** lolos, termasuk navigasi kembali ke landing dari login/sign up; lint, format, pemeriksaan Django, dan pemeriksaan drift migrasi juga lolos. Migrasi sudah diterapkan lokal tanpa reset database. Pemeriksaan HTTP lokal mengonfirmasi redirect login untuk Modul 2/4/5; review visual browser belum tersedia pada sesi alat ini. Deployment PWS belum dilakukan.

**Batas yang masih ada:** cookie guest dapat dihapus atau diganti browser untuk memperoleh trial baru; ini bukan pembatas per orang/IP. Batas Gemini adalah per sesi/hari untuk pengguna login, bukan kuota akun/IP atau pembatas global biaya. Pendaftaran masih menyimpan email sebagai username otomatis; kolom username pilihan pengguna belum diimplementasikan. Deployment PWS belum diverifikasi untuk perubahan otorisasi ini.
