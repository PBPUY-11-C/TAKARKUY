# Modul 4 — Recipe Book & Cooking Tracker

Dokumen ini mencatat implementasi Modul 4 saat ini. Semua halaman dan aksi Recipe Book memerlukan pengguna login. Aksi **Sudah Masak** memakai Pantry Modul 2 untuk memeriksa dan mengurangi stok. Pantry tidak mempunyai sakelar aktivasi terpisah; Pantry yang kosong tetap dapat dibuka dan resep tetap dapat dilihat, tetapi masak hanya bisa dikonfirmasi jika pratinjau menemukan stok cukup atau jumlah batch manual yang valid.

## Rute aktif

| Metode dan rute | Fungsi |
| --- | --- |
| `GET /modul4/` | Daftar/detail resep, filter, favorit, riwayat, dan ulasan. Mendukung `?recipe=<kode>`, `?slot=<id>` untuk resep dari rencana tersimpan, dan `?stock=best` untuk saran resep berdasarkan kecocokan Pantry. |
| `POST /modul4/favorite/` | Simpan atau hapus favorit. |
| `POST /modul4/preview/` | Pratinjau pengurangan stok; tidak mengubah stok. |
| `POST /modul4/cook/` | Konfirmasi masak, mengurangi stok dan mencatat riwayat secara transaksional. |
| `POST /modul4/report-data/` | Kirim laporan data resep yang keliru; laporan dapat ditinjau dan diperbarui statusnya melalui Django Admin. Maksimal 5 laporan per pengguna per jam. |
| `POST /modul4/review/` | Buat/perbarui ulasan setelah pengguna pernah memasak resep. |
| `POST /modul4/review/photo/` | Unggah foto untuk ulasan. Memerlukan login, riwayat masak, ulasan tersimpan, dan persetujuan hak penggunaan foto. |
| `POST /modul4/review/photo/delete/` | Hapus foto milik pengguna dan cabut izinnya tanpa menghapus ulasan tertulis; versi ulasan diperiksa. |
| `GET /modul4/reviews/<id>/photo/` | Tampilkan foto kepada pemilik/moderator, atau kepada pengguna yang login setelah foto disetujui. |
| `POST /modul4/slot-status/` | Tandai slot rencana dilewati atau batalkan status lewati; versi rencana diperiksa agar perubahan usang ditolak. |

## Foto ulasan komunitas

- Pengunggah harus menyatakan bahwa foto miliknya atau ia memiliki izin untuk menggunakannya, serta menyetujui penayangan di TAKARKUY. Foto tanpa persetujuan tidak dapat diunggah.
- Foto yang baru diunggah berstatus menunggu moderasi dan tidak ditampilkan kepada pengguna lain. Moderator dapat menyetujui atau menyembunyikannya; halaman ulasan menampilkan status tersebut kepada pemilik.
- Pemilik dapat menghapus foto dan mencabut izin kapan saja tanpa menghapus rating atau komentar. Penghapusan menaikkan versi ulasan agar tab lama tidak dapat mengubah foto yang lebih baru; berkas dihapus setelah transaksi berhasil. Menghapus seluruh ulasan tetap menghapus foto juga.
- Foto yang sudah disetujui dapat mewakili resep yang belum memiliki foto kurasi. Foto kurasi di `data/mapping/recipe_image_mapping.csv` selalu diprioritaskan.
- Foto komunitas ditampilkan dengan nama publik pengunggah dan atribusi bahwa foto digunakan dengan izin TAKARKUY; ini bukan lisensi terbuka untuk penggunaan ulang di luar aplikasi.

## Penyimpanan dan validasi foto

### Pengembangan lokal

Konfigurasi saat ini memakai `MEDIA_ROOT = BASE_DIR / "media"` dan penyimpanan berkas Django bawaan (`FileSystemStorage` melalui `default_storage`). Proses Django perlu izin tulis ke direktori `media/`; penyimpanan membuat subdirektori `recipe-reviews/<kode-resep>/` saat foto disimpan. Foto disajikan lewat endpoint terautentikasi/moderasi di atas, bukan dengan mengandalkan URL direktori media publik.

Pastikan direktori `media/` dapat ditulis oleh akun yang menjalankan `runserver`. Berkas media lokal adalah data runtime: jangan masukkan foto unggahan ke Git. Untuk menguji unggah, lihat foto yang menunggu moderasi sebagai pemilik, setujui melalui Django Admin, lalu pastikan endpoint foto mengembalikan JPEG.

### Deployment

- Pasang volume persisten yang dapat dibaca dan ditulis proses Django pada `MEDIA_ROOT`, atau konfigurasi `STORAGES["default"]` ke backend penyimpanan persisten yang kompatibel dengan `default_storage`.
- Jika aplikasi berjalan pada beberapa instance, semua instance harus mengakses penyimpanan yang sama. Jangan mengandalkan filesystem container sementara: berkas akan hilang saat instance diganti dan foto di database tidak dapat dibuka.
- Simpan kredensial backend di environment/secret manager, bukan di repo. Sertakan foto komunitas dalam kebijakan backup dan uji operasi simpan, buka, serta hapus berkas setelah deployment.
- Aplikasi tidak memerlukan `MEDIA_URL` publik untuk foto ulasan. Endpoint aplikasi mengirim foto sebagai `image/jpeg` dengan `X-Content-Type-Options: nosniff` dan `Cache-Control: private, no-store`.
- Endpoint foto memerlukan login, termasuk untuk foto yang telah disetujui; “tampil untuk pengguna lain” berarti pengguna yang sudah masuk ke TAKARKUY.

### Batas dan kegagalan unggah

- Request multipart dibatasi sekitar 7 MB untuk memberi ruang overhead form; berkas foto sendiri maksimal 6 MB.
- Hanya gambar yang benar-benar dapat dibaca sebagai JPEG, PNG, atau WebP yang diterima; nilai `Content-Type` dari browser tidak menjadi bukti format. Berkas kosong, rusak, format lain, gambar di atas 40 juta piksel, atau hasil kompresi di atas 6 MB ditolak.
- Foto yang diterima diputar sesuai orientasi EXIF, diperkecil maksimal 1600 × 1600 piksel, dibersihkan dari metadata gambar sumber, dan disimpan ulang sebagai JPEG.
- Jika rekaman ulasan tidak memiliki berkas foto atau berkasnya hilang/tidak dapat dibuka di storage, endpoint foto mengembalikan `404` dengan pesan `Foto tidak tersedia.` atau `Berkas foto tidak ditemukan.`. Pulihkan berkas dari backup atau hapus/ganti foto ulasan; metadata database saja tidak dapat memulihkan gambar.

## Kelengkapan data resep dan laporan koreksi

Kartu dan detail resep menampilkan status panduan, takaran bahan, dan foto. Status takaran dihitung dari bahan yang tertaut serta keberhasilan konversi jumlah bahan ke gram; takaran estimasi diberi penanda tersendiri. Status foto hanya ditampilkan sebagai ditinjau jika tersedia dari pemetaan kurasi atau foto komunitas yang sudah lolos moderasi. Pengguna dapat melaporkan masalah pada bahan/takaran, panduan, foto, atau informasi gizi. Laporan tidak langsung mengubah katalog; tim meninjau dan memperbarui status melalui Django Admin.

Filter stok **Paling cocok dengan stok** memberi urutan resep berdasarkan proporsi kebutuhan bahan utama yang tersedia di Pantry, lalu menunjukkan bahan yang masih kurang. Perhitungan ini hanya saran dan tidak mengunci atau mengurangi stok. Jumlah stok baru berubah setelah pratinjau dan konfirmasi **Sudah Masak**.

Jika resep mempunyai panduan, tombol **Mulai mode memasak** menampilkan langkah satu per satu, checklist bahan, dan timer manual opsional. Mode ini tidak mengubah stok. Pengurangan stok tetap hanya terjadi melalui pratinjau dan konfirmasi **Sudah Masak**.

## Tes Modul 4

Tes terkait berada di berkas berikut:

- `apps/recipe_book/tests.py`: `test_page_filters_and_does_not_reduce_stock`, `test_favorites_are_idempotent_personal_and_inactive_visible`, `test_guidance_visible_by_default_with_optional_guidance_filter`, `test_allergen_index_changes_on_ingredient_link_tag_and_delete`, `test_api_guards_bad_inputs_csrf_and_guest`, `test_stock_filters_are_read_only_and_portion_aware`, `test_best_stock_filter_ranks_recipes_and_explains_missing_ingredients`, `test_best_stock_filter_explains_when_pantry_has_no_matching_stock`, `test_pantry_and_book_agree_on_complete_recipes`.
- `apps/recipe_book/test_slot_status.py`: `test_slot_with_rice_needs_rice_stock_when_cooking`, `test_page_offers_skip_only_for_planned_slots`, `test_price_filter_hides_recipes_above_limit`, `test_recipe_costs_skips_recipes_without_prices`, `test_recipe_costs_quotes_one_recipe_from_multi_meal_catalog`, `test_soon_filter_uses_jakarta_date`.
- `apps/recipe_book/test_reviews.py`: `test_review_pagination_keeps_slot`, `test_public_stats_hide_moderated_reviews_and_never_publish_email`.
- `apps/accounts/tests.py`: `test_modul4_keeps_header_and_shows_recipe_book`.

Nama `test_guidance_hidden_by_default_but_direct_link_explains` yang tertulis di catatan lama sudah tidak berlaku. Resep tanpa panduan tetap muncul secara default, ikut dihitung pada pemberitahuan jumlah resep tanpa panduan, dan diberi label status di kartu resep. Pada detailnya, bagian langkah memasak diganti pesan bahwa panduan belum tersedia atau masih ditahan untuk peninjauan sumber. Filter **Hanya resep dengan panduan** (`?guidance=1`) membatasi daftar ke resep dengan panduan terverifikasi. Resep tersebut masih dapat dilihat dan dipakai untuk estimasi stok/gizi, tetapi halaman tidak menyediakan langkah memasaknya.

## Header dan head bersama

`templates/partials/head.html` dan `templates/partials/app_header.html` dipakai bersama oleh halaman Modul 2 dan Modul 4. Perubahan pada judul/font bersama atau tautan beranda perlu mempertahankan kedua halaman tersebut.

## Checklist integrasi Planner

- [ ] Tombol dari jadwal membuka resep dan slot yang benar. Detail memakai jumlah porsi slot; opsi nasi mengikuti snapshot slot dan porsi tidak bisa diubah dari halaman resep.
- [ ] Perubahan status lewati dan aksi masak mengirim versi rencana terbaru. Versi usang ditolak; penolakan tidak mengurangi stok atau membuat riwayat masak.
- [ ] Pratinjau pemakaian stok tidak mengubah Pantry. Stok baru berkurang setelah konfirmasi masak, dan riwayat tercatat satu kali walau permintaan yang sama dikirim ulang.

Tes otomatis terkait mencakup `test_skip_rejects_stale_version_cooked_slot_and_other_user`, `test_slot_cook_rejects_stale_plan_version_without_consuming_stock`, `test_slot_cook_rejects_portion_different_from_planner_slot`, `test_slot_with_rice_needs_rice_stock_when_cooking`, `test_preview_cook_and_replay_use_same_ledger`, dan `test_slot_cook_updates_plan_version_and_blocks_new_key_double_cook`.

Jalankan tes backend dengan `python manage.py test apps.recipe_book` atau seluruh suite dengan `python manage.py test`. Tes antarmuka JavaScript berada di `apps/recipe_book/tests_js/` dan memerlukan Node.js.
