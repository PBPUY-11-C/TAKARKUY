# Modul 4 — Recipe Book & Cooking Tracker

Dokumen ini mencatat implementasi Modul 4 saat ini. Halaman Recipe Book tersedia di `/modul4/`; fitur memasak dan ulasan memerlukan pengguna login. Aksi **Sudah Masak** memakai Pantry Modul 2 untuk menghitung dan mengurangi stok.

## Rute aktif

| Metode dan rute | Fungsi |
| --- | --- |
| `GET /modul4/` | Daftar/detail resep, filter, favorit, riwayat, dan ulasan. Mendukung `?recipe=<kode>` serta `?slot=<id>` untuk resep dari rencana tersimpan. |
| `POST /modul4/favorite/` | Simpan atau hapus favorit. |
| `POST /modul4/preview/` | Pratinjau pengurangan stok; tidak mengubah stok. |
| `POST /modul4/cook/` | Konfirmasi masak, mengurangi stok dan mencatat riwayat secara transaksional. |
| `POST /modul4/review/` | Buat/perbarui ulasan setelah pengguna pernah memasak resep. |
| `POST /modul4/review/photo/` | Unggah foto untuk ulasan. Memerlukan login, riwayat masak, ulasan tersimpan, dan persetujuan hak penggunaan foto. |
| `GET /modul4/reviews/<id>/photo/` | Tampilkan foto yang boleh dilihat pemiliknya, moderator, atau publik setelah foto disetujui. |
| `POST /modul4/slot-status/` | Tandai slot rencana dilewati atau batalkan status lewati; versi rencana diperiksa agar perubahan usang ditolak. |

## Foto ulasan komunitas

- Pengunggah harus menyatakan bahwa foto miliknya atau ia memiliki izin untuk menggunakannya, serta menyetujui penayangan di TAKARKUY. Foto tanpa persetujuan tidak dapat diunggah.
- Foto yang baru diunggah berstatus menunggu moderasi dan tidak ditampilkan kepada publik. Moderator dapat menyetujui atau menyembunyikannya. Pengguna dapat mencabut persetujuan dengan menghapus foto/ulasannya.
- Foto yang sudah disetujui dapat mewakili resep yang belum memiliki foto kurasi. Foto kurasi di `data/mapping/recipe_image_mapping.csv` selalu diprioritaskan.
- Foto komunitas ditampilkan dengan nama publik pengunggah dan atribusi bahwa foto digunakan dengan izin TAKARKUY; ini bukan lisensi terbuka untuk penggunaan ulang di luar aplikasi.

## Tes Modul 4

Tes terkait berada di berkas berikut:

- `apps/recipe_book/tests.py`: `test_page_filters_and_does_not_reduce_stock`, `test_favorites_are_idempotent_personal_and_inactive_visible`, `test_guidance_visible_by_default_with_optional_guidance_filter`, `test_allergen_index_changes_on_ingredient_link_tag_and_delete`, `test_api_guards_bad_inputs_csrf_and_guest`, `test_stock_filters_are_read_only_and_portion_aware`, `test_pantry_and_book_agree_on_complete_recipes`.
- `apps/recipe_book/test_slot_status.py`: `test_slot_with_rice_needs_rice_stock_when_cooking`, `test_page_offers_skip_only_for_planned_slots`, `test_price_filter_hides_recipes_above_limit`, `test_recipe_costs_skips_recipes_without_prices`, `test_recipe_costs_quotes_one_recipe_from_multi_meal_catalog`, `test_soon_filter_uses_jakarta_date`.
- `apps/recipe_book/test_reviews.py`: `test_review_pagination_keeps_slot`, `test_public_stats_hide_moderated_reviews_and_never_publish_email`.
- `apps/accounts/tests.py`: `test_modul4_keeps_header_and_shows_recipe_book`.

Nama `test_guidance_hidden_by_default_but_direct_link_explains` yang tertulis di catatan lama sudah tidak berlaku. Perilaku sekarang adalah resep tanpa panduan tetap ditampilkan secara default; filter opsional membatasi daftar ke resep yang memiliki panduan terverifikasi.

Jalankan tes backend dengan `python manage.py test apps.recipe_book` atau seluruh suite dengan `python manage.py test`. Tes antarmuka JavaScript berada di `apps/recipe_book/tests_js/` dan memerlukan Node.js.
