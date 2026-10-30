# Modul 4 — Recipe Book & Riwayat Masak

Dokumen ini menjelaskan perilaku dan perubahan Modul 4 yang tidak dijabarkan lengkap di README utama. Modul Django saat ini berada di `apps/recipe/`; label database tetap `recipe_book` agar tabel dan migrasi lama tetap dikenali.

## Alur pengguna

1. Pengguna masuk ke `/recipes/` untuk mencari dan menyaring resep. Halaman hanya menampilkan resep aktif dan siap digunakan, lalu menerapkan preferensi akun seperti alergi dan bahan yang dihindari.
2. Pengguna membuka detail resep untuk melihat foto beserta atribusinya, porsi, informasi bahan, status kecocokan stok, panduan, gizi, dan estimasi harga jika tersedia.
3. Pemeriksaan atau pratinjau stok bersifat baca-saja. Stok Pantry tidak berubah sebelum pengguna menekan konfirmasi memasak.
4. Saat memasak dikonfirmasi, Modul 4 mencatat riwayat dan meminta Modul 2 mengurangi stok dalam alur transaksional. Jika resep dibuka dari rencana Modul 1, status slot rencana juga diperbarui sesuai hasil tindakan.
5. Setelah memasak, pengguna dapat memberi ulasan dan mengirim foto dengan persetujuan hak penggunaan. Foto pengguna dimoderasi sebelum dapat ditampilkan kepada publik.

## Integrasi dan URL

URL halaman utama Recipe Book adalah **`/recipes/`**. Nama URL Django tetap `modul4` untuk menjaga tautan internal, termasuk tautan Planner. URL lama **`/recipe/`** dan **`/modul4/`** mengalihkan ke halaman baru dan mempertahankan query string, misalnya `?slot=...` atau `?recipe=...`.

Endpoint aksi saat ini masih memakai awalan `/modul4/` demi kompatibilitas internal:

| Endpoint | Kegunaan |
| --- | --- |
| `POST /modul4/favorite/` | Menambah atau menghapus favorit pengguna. |
| `POST /modul4/note/` | Menyimpan atau menghapus catatan pribadi resep. |
| `POST /modul4/estimate/` | Menghitung estimasi biaya untuk porsi resep. |
| `POST /modul4/preview/` | Memeriksa pemakaian stok tanpa menguranginya. |
| `POST /modul4/cook/` | Mengonfirmasi masak, mengurangi stok yang dikelola, dan mencatat riwayat. |
| `POST /modul4/report-data/` | Mengirim laporan masalah data resep. |
| `POST /modul4/review/` | Menulis atau mengubah ulasan setelah memasak. |
| `POST /modul4/review/photo/` | Mengunggah foto ulasan yang menunggu moderasi. |
| `POST /modul4/review/photo/delete/` | Menghapus foto ulasan milik pengguna. |
| `GET /modul4/reviews/<id>/photo/` | Menyajikan foto sesuai izin, moderasi, dan hak akses. |
| `POST /modul4/slot-status/` | Mengubah status menu pada rencana, misalnya dimasak atau dilewati. |

Endpoint aksi memerlukan autentikasi dan perlindungan CSRF sesuai jenis permintaannya. Jangan mengubah prefix URL atau nama URL tanpa memperbarui template, JavaScript, tes, dan tautan Planner bersama-sama.

## Perubahan perilaku penting

- **Kuota estimasi terpisah dari Planner.** Estimasi dan pratinjau Recipe Book menggunakan kuota Recipe Book sendiri agar aktivitas mengubah porsi di halaman resep tidak menghabiskan kuota pratinjau Planner.
- **Biaya hanya dihitung untuk resep yang diperlukan.** Filter harga dapat menghitung kandidatnya, sementara halaman biasa membatasi kalkulasi biaya pada resep yang sedang ditampilkan. Ini menghindari penghitungan ulang seluruh katalog untuk setiap halaman.
- **Perubahan porsi memerlukan pemeriksaan ulang stok.** Setelah porsi berubah, status bahan yang dilacak meminta pengguna memeriksa kecocokan stok kembali. Status tersebut tidak menyatakan bahwa tanggal kedaluwarsa bahan tidak diketahui.
- **Foto publik dapat di-cache.** Foto ulasan yang sudah mendapat izin dan persetujuan moderasi menggunakan cache privat satu jam. Foto yang belum disetujui tetap `no-store` dan hanya dapat dilihat oleh pemilik atau staf.
- **Pemrosesan unggahan dibatasi.** Foto dibatasi format dan ukuran, divalidasi serta dinormalisasi sebelum disimpan, dan upaya unggah terkena rate limit. Foto tidak dipublikasikan sebelum moderasi.
- **Data harga yang tidak tersedia tidak boleh dianggap nol.** Estimasi harga hanya ditampilkan bila datanya dapat dihitung; filter dan keterangan halaman perlu menjelaskan bahwa resep tanpa data harga tidak dapat dibandingkan.
- **Halaman tanpa pilihan resep tetap menjadi halaman pencarian.** Detail resep dan pemeriksaan stok disiapkan ketika pengguna memilih resep atau membuka tautan slot Planner, bukan otomatis untuk resep pertama pada hasil pencarian.

## Tampilan dan aset

Template halaman berada di `apps/recipe/templates/recipe/`, sedangkan aset khusus Recipe Book berada di `apps/recipe/static/recipe/`. CSS bersama dan header aplikasi bukan milik Modul 4 dan sebaiknya tidak diubah untuk penyesuaian halaman ini.

`modul4.css` adalah hasil terlingkup untuk `.book-shell` dan `#cooking-dialog`. Sumber desain berada di `tools/takarkuy-modul4-lengkap.css` dan aturan penyesuaian markup berada di `tools/modul4-adapter.css`. Jika sumber atau adapter diubah, buat ulang hasilnya dengan:

```powershell
python tools/scope_css.py tools/takarkuy-modul4-lengkap.css tools/modul4-adapter.css apps/recipe/static/recipe/modul4.css
```

Aturan latar mode gelap Recipe Book menggunakan `#121419`, sama dengan latar halaman Planner. Selector CSS untuk dialog harus mempertahankan bentuk `.modal` pada elemen dialog dan `.modal__*` sebagai elemen turunannya; generator menangani keduanya secara berbeda.

## Foto ulasan dan deployment

Secara default, foto disimpan melalui storage Django lokal di `MEDIA_ROOT`. Ini cocok untuk pengembangan lokal, tetapi filesystem container hosting dapat bersifat sementara atau tidak dibagi antar-instance. Untuk deployment, gunakan disk persisten yang dicadangkan atau object storage yang kompatibel dengan S3 melalui konfigurasi `STORAGES`. Jika perintah pembersihan foto dijalankan melalui worker, pastikan platform hosting menjalankan worker tersebut sebagai proses terpisah dan peringatannya ditinjau.

Perintah operasional tersedia di `apps/recipe/management/commands/` untuk audit dan pembersihan foto. Jalankan sesuai jadwal deployment dan periksa log kegagalan storage; dokumentasi perintah saja tidak berarti worker sudah aktif di hosting.

## Tes dan batas klaim

Tes backend Modul 4 berada di `tests/recipe/`, dan tes JavaScript berada di `tests/js/recipe/`. Jalankan tes pada versi kode setelah konflik merge diselesaikan. Jangan mengutip angka coverage atau jumlah tes lulus dari run sebelumnya sebagai hasil untuk commit baru tanpa menjalankan kembali tes dan laporan coverage pada commit tersebut.

Dokumen ini menjelaskan perilaku yang ada di kode. Keberhasilan worker, persistensi media, konfigurasi storage, dan peninjauan log produksi tetap perlu diverifikasi di platform deployment.
