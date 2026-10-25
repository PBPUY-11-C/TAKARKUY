# Pemetaan foto resep

`data/mapping/recipe_image_mapping.csv` menyimpan foto berlisensi terbuka yang cocok untuk resep. Aplikasi menampilkan foto di kartu Recipe Book, halaman detail Modul 4, dan jadwal Modul 1, bersama kredit pembuat, sumber, dan tautan lisensi. Resep yang belum punya pemetaan menampilkan penanda “Foto belum tersedia”; foto generik tidak digunakan sebagai pengganti.

## File yang dipakai untuk alur foto

| File | Kegunaan |
| --- | --- |
| `docs/recipe_image_mapping.md` | Panduan mencari, meninjau, dan menambahkan foto kurasi katalog. |
| `docs/MODUL4.md` | Panduan unggah, moderasi, dan penghapusan foto ulasan komunitas. |
| `photo_candidates/kandidat_foto.html` | Galeri visual untuk meninjau kandidat foto; pilihan di galeri belum otomatis tampil di aplikasi. |
| `photo_candidates/kandidat_foto.csv` | Daftar kandidat beserta sumber, kredit, dan lisensi untuk galeri. |
| `data/mapping/recipe_image_mapping.csv` | Pemetaan foto kurasi yang dibaca aplikasi. Admin mengedit file ini untuk menambah atau mengganti foto utama resep. |
| `data/mapping/themealdb_recipe_curation.csv` | Keputusan kurasi kandidat resep TheMealDB; bukan daftar foto ulasan pengguna. |
| `data/scratch/themealdb_100_candidates.csv` dan `data/scratch/themealdb_western_100_candidates.csv` | Snapshot kandidat resep TheMealDB untuk ditinjau dan dipromosikan ke katalog; bukan pemetaan foto aktif. |
| `data/scratch/themealdb_western_100_candidates.json` | Snapshot JSON kandidat yang sama, termasuk data sumber lebih lengkap untuk kurasi. |

Persetujuan foto komunitas dilakukan di **Django Admin → Recipe reviews**, bukan dengan mengedit file CSV. Foto komunitas yang disetujui hanya menjadi cadangan jika resep belum memiliki foto kurasi. Lihat [dokumentasi Modul 4](MODUL4.md) untuk langkah moderasi.

## Mencari foto untuk resep tanpa foto

`photo_candidates/cari_foto_belum_ditemukan.py` mencari resep aktif yang dapat dijadwalkan tetapi belum ada di mapping. Nama pencarian mengikuti nama tampilan katalog: nama override kurasi dari `mapping/recipe_name_overrides.csv`, lalu aturan ejaan dan kapitalisasi dari `data/recipe_names.py`. Nama TheMealDB yang sudah dikurasi manual dipertahankan. Pencarian menggunakan Openverse, yang mengindeks gambar dari berbagai penyedia seperti Wikimedia Commons dan Flickr. Pencarian mencoba nama Indonesia, kata bahan, dan padanan bahasa Inggris. Hasil harus memiliki kecocokan kata yang cukup pada judul gambar dan lisensi yang mengizinkan penggunaan komersial (CC0, Public Domain Mark, CC BY, atau CC BY-SA). Pencarian versi terbaru hanya menambahkan satu kandidat prioritas per resep.

Jalankan dari folder `photo_candidates`:

```powershell
python .\cari_foto_belum_ditemukan.py --limit 25
```

Setelah resep TheMealDB dikurasi, dipromosikan ke katalog aktif, dan fixture katalog diimpor, cari foto khusus untuk resep dari sumber TheMealDB dengan:

```powershell
python .\cari_foto_belum_ditemukan.py --source themealdb --limit 100
```

Opsi `--source themealdb` hanya memilih resep katalog dengan sumber `TheMealDB API` yang aktif, dapat dijadwalkan, dan belum punya foto terpetakan/kandidat Openverse (atau yang diminta untuk dicari ulang). Snapshot kandidat di `data/scratch/themealdb_western_100_candidates.*` belum memenuhi syarat tersebut. Gambar thumbnail dari TheMealDB juga ada di snapshot, tetapi hanya gunakan jika hak pakainya jelas; periksa kredit/lisensi dan tautkan kembali ke halaman TheMealDB.

`--limit 25` membatasi pencarian ke 25 resep setiap sesi. Jalankan lagi untuk mengambil batch berikutnya. Hasil disimpan bertahap ke `kandidat_foto.csv` dan galeri `kandidat_foto.html`, jadi kandidat yang terkumpul sebelumnya tetap ada. Untuk mengulang pencarian pada resep yang sebelumnya belum mendapat hasil, tambahkan `--retry-unfound`.

Galeri membantu memeriksa banyak hasil sekaligus. Skor kata hanya menilai metadata judul, bukan mengenali isi visual; karena itu foto kandidat tetap perlu dicek apakah benar-benar menampilkan hidangan tersebut, lalu kredit dan lisensinya diperiksa. Menemukan kandidat tidak otomatis mengubah aplikasi: setelah memilih foto yang cocok, tambahkan barisnya ke `data/mapping/recipe_image_mapping.csv` agar foto tampil di produk. Pencarian yang tidak menemukan kandidat kuat membiarkan resep tanpa foto, bukan mengisi dengan gambar generik.

### Meninjau pilihan di galeri

1. Jalankan pencarian kandidat, lalu buka `photo_candidates/kandidat_foto.html` di browser.
2. Periksa gambar dan buka **halaman sumber** untuk memastikan gambarnya benar-benar hidangan tersebut. Verifikasi pembuat dan lisensi di halaman sumber; skor kecocokan judul saja tidak cukup.
3. Klik **Pilih foto** untuk paling banyak satu gambar per resep. Pilihan disimpan di `localStorage` browser yang sama; klik **Unduh pilihan (CSV pemetaan)** sebelum membersihkan data browser atau berpindah perangkat.
4. Buka `foto_resep_dipilih.csv` yang terunduh. Gabungkan baris datanya (tanpa header kedua) ke `data/mapping/recipe_image_mapping.csv`. Pastikan hanya ada satu pemetaan terpilih untuk tiap `recipe_code`, lalu segarkan halaman aplikasi.

Galeri ini menampilkan kandidat dari `kandidat_foto.csv`; ia tidak mengubah file pemetaan utama atau database. Django Admin hanya menampilkan status foto pada resep, belum menyediakan form untuk mengelola pemetaan gambar.

### Dua jalur foto dan urutan tampil

Foto katalog dan foto komunitas dikelola lewat jalur berbeda:

1. **Foto kurasi katalog** dikelola admin di `data/mapping/recipe_image_mapping.csv`. Foto ini menjadi gambar utama resep.
2. **Foto komunitas** diunggah pengguna sebagai bagian dari ulasan, lalu menunggu moderasi di Django Admin. Foto ini hanya menjadi cadangan untuk resep yang belum memiliki foto kurasi.

Urutan ini disengaja: jika ada pemetaan kurasi untuk resep, foto komunitas yang disetujui tidak menggantikannya. Persetujuan foto komunitas hanya mengizinkan penayangan di TAKARKUY; persetujuan itu bukan lisensi terbuka untuk penggunaan di luar aplikasi.

### Admin menambahkan foto kurasi

Saat ini Django Admin belum menyediakan formulir untuk menambah atau mengubah pemetaan foto katalog. Admin menambahkan atau mengganti foto dengan mengedit `data/mapping/recipe_image_mapping.csv`. Gunakan kode resep aktif yang tepat, URL gambar langsung yang dapat dibuka, URL halaman sumber, nama pembuat, nama dan URL lisensi/izin, serta judul file. Jika admin mengambil foto sendiri, cantumkan admin sebagai pembuat dan pastikan izin penggunaan serta atribusinya jelas. Contoh format berikut hanya menunjukkan kolom; jangan salin nilai contohnya:

```csv
recipe_code,image_url,source_url,creator,license_name,license_url,file_title
RCP-CONTOH-001,https://cdn.example.org/foto.jpg,https://sumber.example.org/resep,Nama Pembuat,CC BY 4.0,https://creativecommons.org/licenses/by/4.0/,Nama foto.jpg
```

Sebelum menyimpan baris, admin memeriksa bahwa gambar benar-benar menampilkan hidangan yang dimaksud, halaman sumber cocok, dan hak penggunaan mengizinkan penayangan. Jangan isi lisensi berdasarkan tebakan. Bila halaman sumber tidak menunjukkan lisensi atau izin penggunaan, jangan masukkan foto ke mapping kurasi sampai hak pakainya dipastikan. Snapshot kandidat Barat menyimpan URL thumbnail TheMealDB, tetapi `image_credit` kosong untuk 100 kandidat yang dikumpulkan; keberadaan URL tidak membuktikan izin penggunaan. Ketentuan TheMealDB meminta pemeriksaan `strCreativeCommons`, tautan kembali ke sumber bila sesuai, serta izin atau dasar legal untuk konten pihak ketiga.

Setelah CSV disimpan, aplikasi membaca ulang mapping ketika metadata file berubah; tidak perlu migrasi atau impor katalog. Pastikan hanya ada satu pemetaan untuk tiap `recipe_code`. Jika mengganti foto, ganti baris pemetaan resep tersebut. Muat ulang halaman dan pastikan `recipe_code` sama persis dengan kode resep aktif. Foto lokal yang hanya ada di komputer admin tidak dapat dipakai melalui CSV oleh pengguna/deployment lain; gunakan URL yang dapat diakses oleh aplikasi atau proses penyimpanan aset yang dipakai deployment.

TheMealDB dapat menjadi sumber tambahan, tetapi area Indonesia pada katalognya saat ini tidak mengembalikan daftar hidangan. Karena itu pencarian untuk resep yang sudah ada menggunakan Openverse sebagai pengindeks lintas penyedia; hasil foto tetap dikaitkan ke halaman sumber dan lisensi masing-masing.
