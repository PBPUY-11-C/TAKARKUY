# Snapshot sumber

Folder ini menyimpan snapshot sumber pada 28 September dan 1 Oktober 2026. Aplikasi tidak membaca file di sini secara langsung; CSV hasilnya ada di `../processed/` dan `../mapping/`. `manifest.json` mencatat URL asal, ukuran, dan SHA-256 untuk sumber utama.

- `tkpi_2020.pdf`: TKPI Kemenkes berupa pindai; belum diekstrak menjadi nilai gizi.
- `bapanas_fresh_nutrition.html`: tabel komposisi pangan segar resmi Badan Pangan Nasional; 64 entri diekstrak ke `mapping/bapanas_nutrition_snapshot.json`.
- `garut_prices_2026-09-28.html`: halaman harga Disperindag Kabupaten Garut; 78 komoditas pangan dipakai sesudah mengecualikan gas.
- `pihps_prices_2026-09-28.json`: respons snapshot harga PIHPS Bank Indonesia untuk 21 komoditas nasional.
- `indonesian_food_recipes.zip`: arsip Kaggle yang diperlukan generator/audit. Dari 60 kandidat, 17 kini siap dihitung dengan takaran/porsi estimasi dan langkah adaptasi TAKARKUY; 43 masih diblokir. Ada pula 20 resep internal lama yang terinspirasi Kaggle. Arsip tetap disimpan sebagai jejak sumber, bukan duplikat katalog aktif.
- `usda_sr_legacy_2018-04.zip`: USDA FoodData Central, fallback untuk beberapa bahan dan dasar dua konversi ukuran.
- `foodkeeper_mirror_2019.csv`: cermin historis FoodKeeper. Unduhan resmi tidak berhasil diakses saat paket dibuat; setiap umur simpan diberi status referensi yang perlu verifikasi lokal.
- `openfoodfacts_indonesia_sample.json`: snapshot kecil Open Food Facts (1 Oktober 2026), bukan katalog seluruh toko. Produk mentah dipertahankan untuk jejak asal; indeks pemeriksaan ada di `../staging/openfoodfacts_products.csv`. Data pengguna dan lisensi ODbL perlu ditinjau sebelum dimasukkan ke katalog aktif.
