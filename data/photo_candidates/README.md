# Alat kurasi kandidat foto

Direktori ini berisi alat kerja untuk mencari dan meninjau kandidat foto resep. Ini bukan bagian runtime aplikasi Django.

## File aktif

- `cari_foto_belum_ditemukan.py` mencari kandidat berlisensi yang berpotensi cocok dari Openverse.
- `kandidat_foto.csv` menyimpan metadata kandidat, termasuk sumber, kredit, lisensi, dan status tinjauan.
- `kandidat_foto.html` adalah galeri untuk memeriksa gambar secara visual dan memilih kandidat.

Jalankan skrip dari root repository:

```powershell
python .\data\photo_candidates\cari_foto_belum_ditemukan.py --limit 25
```

Galeri dan CSV hanya membantu proses kurasi; keduanya tidak mengubah foto yang ditampilkan aplikasi. Foto terpilih harus diperiksa sumber dan hak pakainya, lalu dimasukkan ke `data/mapping/recipe_image_mapping.csv`. Petunjuk lengkap ada di [../../docs/recipe_image_mapping.md](../../docs/recipe_image_mapping.md).

## Arsip

`archive/` berisi snapshot CSV lama dan daftar resep sumber yang tidak dibaca oleh skrip aktif. Arsip dipertahankan sebagai bahan penelusuran; file yang sedang dipakai adalah CSV dan HTML di direktori utama ini.
