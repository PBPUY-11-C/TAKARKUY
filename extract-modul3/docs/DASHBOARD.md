# Modul 5 — dashboard, ulasan, dan peta

`/modul5/` wajib login. Dashboard hanya membaca data pribadi akun tersebut;
tidak menampilkan angka contoh, uang dihemat, atau limbah dicegah.

## Dashboard

- Hari ini menggunakan **Asia/Jakarta**, bukan tanggal UTC server/runner.
- Semua rencana tersimpan yang sudah mulai dan tanggal menu terakhirnya belum
  lewat ditampilkan terpisah. Draft, rencana masa depan/selesai, serta rencana
  akun lain tidak dihitung. Menu hari ini mengikuti `PlannedMeal.scheduled_on`.
- Nama memakai snapshot. Slot dimasak/dilewati tidak menawarkan aksi masak baru;
  tautan slot membuka Recipe Book dan tidak langsung mengurangi stok.
- Estimasi sisa budget **per rencana** = `inputs.budget - snapshot.total`.
  Ini alokasi estimasi seluruh rencana, bukan saldo/belanja/penghematan aktual.
  Data kosong tampil belum tersedia; negatif tampil estimasi melebihi budget.
- Stok aktif positif dipisah menjadi ≤2 hari lagi, lewat tanggal, dan tanggal
  belum diketahui. Maksimal tiga baris per kelompok, sisanya tetap di Pantry.
  Label/manual/estimasi/legacy dibedakan. `expiry_source=unknown` tetap dianggap
  belum diketahui meski ada tanggal lama. Tidak ada asumsi aman dimakan.
- Total masak berasal dari `CookingHistory`, bukan jumlah menu/ledger/batch;
  tiga riwayat terakhir memakai WIB. Menghapus rencana tidak mengubah total masak.
- `dashboard_data()` menggunakan enam query dengan rencana aktif (lima jika
  prefetch kosong), sekitar delapan full GET termasuk sesi/autentikasi. Agregasi,
  prefetch dan window SQL mencegah N+1 serta membatasi tiga batch per kategori.
- Respons menggunakan `Cache-Control: private, no-store`.

## Ulasan

UI di `/modul4/?recipe=<kode>#recipe-reviews`, bukan panel besar di dashboard.
Dashboard menghubungkan riwayat masak ke bagian ulasan.

- POST JSON `/modul4/review/`: `recipe_code`, `action` (`save`/`delete`), `version`
  (null saat membuat; versi yang dibaca saat edit/hapus), `rating` (integer 1–5),
  `comment` (teks maksimal 500 karakter).
- Setiap save memeriksa `CookingHistory(user, recipe)`. Riwayat setelah rencana
  dihapus tetap memenuhi syarat. Akun lain tidak bisa memakai riwayat tersebut.
- Constraint unik `(user, recipe)`; kunci akun dan cek versi mencegah balapan,
  klik ganda dan tab usang menimpa ulasan. API tidak menerima pemilik dari client.
- Kuota database: 10 upaya valid-format per akun per jendela 10 menit. Penolakan
  riwayat/versi tetap dihitung. HTTP 429 membawa `Retry-After`; logout/worker/browser
  lain tidak mereset. Ulasan terlihat pengguna lain, bukan catatan pribadi.
- Username legacy berupa email diganti `Penakar #<12 karakter heksadesimal>`
  dari HMAC ID akun dengan secret server, bukan ID berurutan atau hash polos.
  Alias stabil selama secret tetap; rotasi secret mengubah alias tanpa mengubah
  ulasan. Email profil tidak ditampilkan. Template meng-escape komentar;
  JavaScript memakai `textContent`.
- Rata-rata dan jumlah dihitung di database dari `is_hidden=False`, bukan dari
  halaman yang dipaginasi. Lima ulasan per halaman.
- Admin dapat menyembunyikan ulasan. Edit pengguna tidak membatalkan moderasi;
  Admin tidak membuat ulasan atas nama pengguna. Akun/resep dihapus → ulasan
  CASCADE; nonaktif tidak menghapusnya. Riwayat tetap mengikuti snapshot Modul 4.
- POST, akun dan CSRF wajib; delete hanya ulasan sendiri.

## Peta dan sumber

Modal memakai Leaflet 1.9.4, baru dimuat setelah klik dengan SRI CSS/JS resmi.
Daftar tetap tersedia saat CDN/tile gagal. Tidak ada polling/autocomplete.

`apps/dashboard/places.json` merupakan kurasi kecil, bukan daftar nasional:

- Guntur Ciawitali, Kadungora dan Cikajang: sumber
  [Disperindag Garut](https://bapokting.disperindag.garutkab.go.id/Gis_pasar).
  Koordinat berasal dari tautan Rute masing-masing, bukan tebakan.
- BSI Rumah Harum Depok: alamat menurut
  [direktori Info3R KLH](https://info3r.kemenlh.go.id/daerah/index/search/a2124d1a0a2c1b1dec9c2aa5d5899b6c/?offset=271).
  **Koordinat belum diverifikasi**: tanpa marker/jarak; tautan membuka pencarian
  nama/alamat, bukan titik pasti. Dataset mencatat tanggal tinjauan dan sumber.

Konfirmasi lokasi, operasional dan jenis sampah yang diterima. Tidak semua bank
sampah menerima sisa makanan. Hasil kosong berarti data belum tersedia, bukan
wilayah itu tidak memiliki fasilitas.

### GPS dan privasi

- GPS hanya setelah klik. Jika izin ditolak, pencarian wilayah manual tetap jalan.
- GPS tidak dikirim ke server aplikasi/database/cookie/localStorage/log. Jarak
  garis lurus dihitung di browser untuk titik terverifikasi pada daftar saat ini,
  bukan pencarian nasional semua tempat terdekat. API menolak field koordinat.
- Jangan masukkan alamat pribadi: backend mencari nama kota/kabupaten.
- Tile/CDN pihak ketiga dapat melihat IP dan area peta yang dibuka. UI menjelaskan
  batas ini; tidak menjanjikan anonimitas terhadap penyedia tile.
- `Referrer-Policy: strict-origin-when-cross-origin` mengirim hanya origin situs,
  bukan path rencana/profil privat, agar sesuai kebijakan tile OSM.

### Daring opsional

Default **nonaktif**, kurasi tetap berjalan tanpa API key. Operator wajib membuat
keputusan sadar dan mematuhi [kebijakan Nominatim](https://operations.osmfoundation.org/policies/nominatim/),
[tile OSM](https://operations.osmfoundation.org/policies/tiles/) dan
[Overpass](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html).
Data terbuka tidak berarti server publik tak terbatas atau dijamin tersedia.

Untuk eksperimen skala kecil, setelah membaca kebijakan, gunakan environment:

```ini
MAP_LOOKUP_ENABLED=true
MAP_USER_AGENT=TAKARKUY/1.0 (+https://github.com/PBPUY-11-C/TAKARKUY)
```

Gunakan kontak aplikasi yang benar-benar dapat dihubungi. Penyedia dapat diganti
via `MAP_GEOCODER_URL`, `MAP_OVERPASS_URL`, `MAP_TILE_URL`. Backend hanya HTTPS,
menolak redirect. Untuk trafik besar pilih penyedia/self-hosted yang sesuai.

- Panggilan hanya setelah submit; tidak ada autocomplete, reverse GPS, prefetch,
  unduhan massal atau pencarian otomatis saat dashboard dibuka.
- Nominatim mencari pusat wilayah Indonesia; Overpass maksimal 30 pasar/tempat
  bernama bank sampah dalam kotak sekitar pusat (±0,08°), bukan seluruh batas
  administrasi. Hasil komunitas perlu dikonfirmasi.
- Cache publik database tujuh hari, bukan data akun/GPS. Cache geocoding wilayah
  dibagi lintas filter; hanya hasil wilayah administratif diterima. Wilayah tidak
  ditemukan disimpan satu hari. Error tidak dianggap
  hasil sukses. Lease/cooldown `MapProviderGate` global lintas worker/akun: tidak
  ada panggilan bersamaan, cooldown 1,1 detik setelah selesai menjaga Nominatim
  di bawah 1 request/detik seluruh aplikasi. Provider sibuk → HTTP 200 daftar
  kurasi dengan pesan sibuk dan `retry_after`, tanpa retry loop/cache error.
- Kuota akun database 10 pencarian **daring yang diaktifkan** per 10 menit,
  termasuk cache/hasil kosong/upaya provider sibuk. Kuota akun habis tetap
  HTTP 429 + `Retry-After`; tidak ditelan fallback. Pencarian offline atau
  daring yang belum diaktifkan operator tidak membuat/mengurangi kuota.
- Transport subprocess: deadline 8 detik/provider, timeout socket 6 detik,
  maksimal 512 KB, tanpa redirect. `finally` melepas kunci; lease kedaluwarsa bila
  worker mati. Error tidak menampilkan body/query upstream.
- Error/hasil daring kosong → kurasi. Wilayah tanpa kurasi mendapat pesan jujur.
- Layanan luar di-mock dalam tes. Tes JS menggunakan DOM tiruan, bukan screenshot
  visual atau pembuktian bahwa peta/lokasi live selalu tersedia.

## Deploy dan pekerjaan terpisah

Verifikasi lokal sebelum revisi kecil audit, 6 Oktober 2026: 422 tes Django lulus di PostgreSQL terisolasi
tanpa skip, 48 tes JS lulus, termasuk 41 tes Python terarah dashboard/ulasan/peta.
Lint, system check, cek migrasi dan validator katalog/kandidat/dokumentasi lulus.
GET lokal guest mengarah ke login; aset dashboard/ulasan membalas 200. Migrasi
diterapkan lokal tanpa reset. Browser tidak tersedia: visual dan provider live
belum diverifikasi. PWS tidak diakses atau diubah. Perubahan Modul 5 berada
pada branch `modul-5-dashboard`; status CI dan merge mengikuti GitHub.

Sesudah revisi kuota offline, fallback provider sibuk, dan alias HMAC: 44 tes
Python terarah lulus di PostgreSQL tanpa skip, 48 tes JS lulus, serta lint,
system check, cek migrasi dan validator dokumentasi lulus. Suite penuh belum
diulang setelah revisi kecil ini; job PostgreSQL CI tetap wajib sebelum merge.

Jalankan `python manage.py migrate --noinput` kemudian
`python manage.py collectstatic --noinput`. Migrasi hanya menambah ulasan, kuota,
cache dan gate; tidak menghapus akun/stok/rencana/riwayat/katalog.
Tidak perlu impor ulang fixture katalog untuk Modul 5.

Sebelum demo, temuan audit auth tetap terpisah: bucket login global per akun bisa
dipakai mengunci korban, dan CIDR proxy PWS perlu diverifikasi agar bucket IP
tidak menghitung seluruh situs sebagai satu IP. Tidak dibuat endpoint diagnostik
publik. Statistik penghematan/limbah dicegah, harga aktual, user-created recipes
dan integrasi stok ke belanja planner tetap belum tersedia.
