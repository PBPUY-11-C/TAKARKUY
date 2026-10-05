# Akun, preferensi, dan maintenance

## Identitas dan akses

`User` Django tetap dipakai; akun lama tidak digabung, dihapus, atau diganti
username-nya. Signup meminta username ASCII 3–30 karakter tanpa `@`, nama,
email, dan password. Username baru serta email dinormalisasi ke huruf kecil.
Index database pada `lower(username)` dan `lower(email)` mencegah duplikasi
kapital, termasuk ketika dua request berjalan bersamaan. Email kosong akun
legacy tidak dibatasi oleh index email. Preflight migrasi menolak duplikasi
dan benturan username legacy dengan email akun lain, sebelum membuat index.
Jika gagal, tinjau data manual; jangan reset schema.

`UsernameOrEmailBackend` tetap melalui `authenticate`, pengecekan password,
dan status aktif Django. Input dengan `@` mencari email, lalu username legacy
jika tidak ada email yang cocok. Input lain hanya mencari username. Tidak ada
Google OAuth, verifikasi email, atau pengiriman reset password pada tahap ini.

`/modul3/` hanya mengelola pengguna yang sedang login, bukan ID dari browser.
`UserProfile` dibuat saat diperlukan melalui `get_or_create`. Edit akun dan
preferensi wajib menyertakan versi; konflik tab lama menghasilkan 409.
Transaksi menulis dengan urutan lock akun → profil. Email baru membutuhkan
password saat ini, yang diperiksa ulang setelah lock. PasswordChangeForm
memvalidasi password lama/baru; update_session_auth_hash mempertahankan sesi
perangkat saat ini. Sesi perangkat lain dengan hash password lama menjadi
tidak valid.

## Kuota login dan signup

`AuthRateBucket` dibagi semua worker melalui database, bukan cache lokal atau
session. Per jendela tetap 15 menit:

| Aksi | Identitas | IP |
| --- | ---: | ---: |
| Login publik/admin | 10 | 100 |
| Signup | 5 per email | 30 |

Username/email milik akun yang sama memakai counter identitas yang sama.
Semua percobaan, termasuk sukses, dihitung. Increment bersyarat dan transaksi
atomik mencegah request paralel melompati slot terakhir. Penolakan 429
menyertakan Retry-After. Kunci HMAC tidak menyimpan email/IP/password asli.
Ini bukan perlindungan sempurna terhadap botnet; jendela tetap memungkinkan
burst ketika berganti jendela.

Default menggunakan REMOTE_ADDR. X-Forwarded-For hanya digunakan jika peer
berasal dari AUTH_TRUSTED_PROXY_CIDRS yang benar-benar diverifikasi operator.
Rantai diperiksa dari kanan hingga alamat pertama yang tidak dipercaya;
header rusak/terlalu panjang kembali ke peer. Jangan percaya seluruh internet.
Jika PWS hanya meneruskan IP proxy dan daftar ini belum dikonfigurasi, batas
IP dibagi oleh pengunjung. Kode tidak menebak CIDR infrastruktur PWS.

## Data alergi dan snapshot

Input kurasi: `data/mapping/ingredient_allergens.csv`. Build menghasilkan
`data/processed/ingredient_allergens.csv` dan metadata master bahan/fixture.
201 bahan memakai ID katalog dan 9 kelompok eksplisit: telur, susu, kacang
tanah, kedelai, gluten/gandum, ikan, krustasea, moluska, wijen. Bahan baru
tanpa mapping otomatis unknown. Review jenis bahan bukan pemeriksaan label
merek maupun sertifikasi bebas alergen.

Saat ada alergi, `apps.catalog.allergens.recipe_allowed` menolak bahan unknown,
metadata invalid, alergen yang dipilih, dan resep dengan bumbu minor yang tidak
dicatat. Bahan opsional juga diperiksa. Filter tidak dilonggarkan untuk budget
atau variasi. Tanpa alergi, perilaku katalog sebelumnya dipertahankan.

Profil mengisi nilai awal rencana baru. Bahan yang ingin dihindari bukan alergi
dan boleh diubah per rencana. Ganti Menu/Cari Menu Lain memakai gabungan alergi
snapshot dan profil saat ini. Profil diperiksa ulang dalam transaksi penerapan
preview/penulisan draft, sehingga perubahan setelah preview menghasilkan 409
jika tidak lagi sesuai. Snapshot lama tidak ditulis ulang; UI memberi peringatan.
Menghapus alergi dari profil tidak menghapus batas pada rencana lama.

Saat implementasi ini: 167 bahan reviewed dan 34 unknown, dengan sekitar
27–31 resep lolos per alergi tunggal dari 296 resep aktif. Kurasi komposisi
produk olahan serta bumbu diperlukan untuk memperluas pilihan. Jangan
mengubah unknown menjadi reviewed hanya untuk menambah hasil. Ini bukan
jaminan bebas alergen; selalu periksa label dan kontaminasi silang. Cakupan
9 kelompok tidak mewakili seluruh jenis alergi.

## PWS

Setelah backup dan deployment kode, jalankan:

```sh
python manage.py migrate --noinput
python manage.py import_catalog data/fixtures/catalog_seed.json
python manage.py collectstatic --noinput
```

Backend baru dapat membuat sesi lama perlu login ulang, tanpa menghapus akun.
Metadata alergen belum tersedia sebelum impor; filter alergi akan menutup
bahan unknown. Pastikan akun staff/superuser dapat login sebelum maintenance.

`MAINTENANCE_MODE=true` lalu restart/redeploy menutup landing, login/signup
publik, semua modul dan API bagi guest/non-staff dengan 503, no-store, serta
Retry-After. Admin tetap memakai autentikasi/izin/CSRF Django; akun staff aktif
bisa melanjutkan pengembangan. Tidak ada bypass query/header. Untuk membuka,
set false lalu restart/redeploy. Default false; environment lokal tidak
mengubah environment PWS. Ini bukan penghentian container atau kunci database;
command background dan admin masih bisa mengubah data.

Pengujian: `apps.accounts.test_profiles`, `test_concurrency`, `test_maintenance`,
dan `apps.budget_planner.test_allergens`. Tes konkurensi harus dijalankan di
PostgreSQL; SQLite bukan bukti row lock. Pengujian lokal tidak mengubah PWS.
