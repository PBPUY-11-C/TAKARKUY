# Pemetaan foto resep

`data/mapping/recipe_image_mapping.csv` menyimpan foto berlisensi terbuka yang cocok untuk resep. Aplikasi menampilkan foto di kartu Recipe Book, halaman detail Modul 4, dan jadwal Modul 1, bersama kredit pembuat, sumber, dan tautan lisensi. Resep yang belum punya pemetaan menampilkan penanda “Foto belum tersedia”; foto generik tidak digunakan sebagai pengganti.

## Mencari foto untuk resep tanpa foto

`photo_candidates/cari_foto_belum_ditemukan.py` mencari resep aktif yang dapat dijadwalkan tetapi belum ada di mapping. Nama pencarian mengikuti nama tampilan katalog: nama override kurasi dari `mapping/recipe_name_overrides.csv`, lalu aturan ejaan dan kapitalisasi dari `data/recipe_names.py`. Nama TheMealDB yang sudah dikurasi manual dipertahankan. Pencarian menggunakan Openverse, yang mengindeks gambar dari berbagai penyedia seperti Wikimedia Commons dan Flickr. Pencarian mencoba nama Indonesia, kata bahan, dan padanan bahasa Inggris. Hasil harus memiliki kecocokan kata yang cukup pada judul gambar dan lisensi yang mengizinkan penggunaan komersial (CC0, Public Domain Mark, CC BY, atau CC BY-SA). Pencarian versi terbaru hanya menambahkan satu kandidat prioritas per resep.

Jalankan dari folder `photo_candidates`:

```powershell
python .\cari_foto_belum_ditemukan.py --limit 25
```

`--limit 25` membatasi pencarian ke 25 resep setiap sesi. Jalankan lagi untuk mengambil batch berikutnya. Hasil disimpan bertahap ke `kandidat_foto.csv` dan galeri `kandidat_foto.html`, jadi kandidat yang terkumpul sebelumnya tetap ada. Untuk mengulang pencarian pada resep yang sebelumnya belum mendapat hasil, tambahkan `--retry-unfound`.

Galeri membantu memeriksa banyak hasil sekaligus. Skor kata hanya menilai metadata judul, bukan mengenali isi visual; karena itu foto kandidat tetap perlu dicek apakah benar-benar menampilkan hidangan tersebut, lalu kredit dan lisensinya diperiksa. Menemukan kandidat tidak otomatis mengubah aplikasi: setelah memilih foto yang cocok, tambahkan barisnya ke `data/mapping/recipe_image_mapping.csv` agar foto tampil di produk. Pencarian yang tidak menemukan kandidat kuat membiarkan resep tanpa foto, bukan mengisi dengan gambar generik.

TheMealDB dapat menjadi sumber tambahan, tetapi area Indonesia pada katalognya saat ini tidak mengembalikan daftar hidangan. Karena itu pencarian untuk resep yang sudah ada menggunakan Openverse sebagai pengindeks lintas penyedia; hasil foto tetap dikaitkan ke halaman sumber dan lisensi masing-masing.
