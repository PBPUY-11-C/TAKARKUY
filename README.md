# TAKARKUY

**TAKARKUY** (Tata Kelola Anggaran dan Resep, Kuy!) adalah aplikasi web khusus untuk membantu pengguna merencanakan menu makanan yang sehat, hemat, dan minim limbah makanan. Berbeda dari aplikasi resep konvensional, TAKARKUY memulai perencanaan dari anggaran dan stok bahan yang sudah tersedia, kemudian menyusun rekomendasi menu untuk hari-hari selanjutnya.

## Status Implementasi

Snapshot kode dan dataset: **1 Oktober 2026**. Bagian visi, perbandingan, CRUD, dan integrasi di bawah menjelaskan **cakupan/rencana produk**, bukan klaim bahwa seluruh fiturnya sudah selesai.

| Bagian | Sudah tersedia | Belum tersedia |
| --- | --- | --- |
| Modul 1 | Simulasi budget, kombinasi target gizi, pantangan, jadwal menu, daftar belanja, dan estimasi gizi/biaya dari katalog lokal. | CRUD card rencana tersimpan dan integrasi stok pantry. |
| Modul 2 | OCR Tesseract.js, fallback foto Gemini, koreksi tabel, input manual, saran nama/penyimpanan, tabel stok, ubah lokasi/tanggal kedaluwarsa, dan hapus stok. | Stok milik akun lintas perangkat, edit seluruh kolom stok setelah disimpan, pengingat otomatis, dan integrasi cuaca/pengurangan stok saat memasak. |
| Modul 3 | Landing, daftar akun, login/logout, validasi kata sandi, dan Django Admin. | Username pilihan pengguna, Google OAuth, serta halaman profil/preferensi. |
| Modul 4 | Template halaman dengan header dan tautan kembali ke beranda. | Recipe book, favorit, dan cooking tracker. |
| Modul 5 | Beranda setelah login dengan navigasi Budget Meal Planner, Smart Pantry, dan Recipe Book. | Statistik penghematan, ulasan makanan, dan market locator. |

Katalog saat ini berisi **187 bahan, 143 catatan harga, dan 247 resep; 108 resep siap dihitung**, sedangkan 139 masih diblokir karena datanya belum lengkap. Ada **231 kandidat produk Open Food Facts** dan **1.500 kandidat resep** terpisah untuk kurasi, bukan tambahan otomatis ke katalog aktif. Rincian sumber, asumsi, dan penghalang ada di [data/DATASETS.md](data/DATASETS.md).

## Anggota Kelompok

| Nama | NPM |
| --- | --- |
| Alfredo Nathaniel Putra Harsono | 2506656412 |
| Alena Aura Deviyana | 2506656394 |
| Aiko Zahwa | 2506617140 |
| Attar Rais Hakam | 2506656495 |
| Rajendra Akbar Mahdiansyah | 2506596874 |

## Latar Belakang dan Value Proposition

### Visi

TAKARKUY bertujuan mendukung pola konsumsi pangan yang terencana, efisien secara finansial, dan ramah lingkungan. Aplikasi ini ingin membuat pola makan sehat yang terjangkau lebih mudah diakses masyarakat Indonesia tanpa menyisakan bahan makanan yang terbuang.

### Masalah yang Diselesaikan

- **Food waste rumah tangga:** bahan makanan terlupakan, kedaluwarsa, atau membusuk karena pengguna tidak tahu kapan harus mengolahnya.
- **Budget belanja tidak efisien:** pengguna kesulitan membagi anggaran makan harian atau mingguan secara realistis.
- **Nutrisi terabaikan demi hemat:** penghematan sering dilakukan dengan mengorbankan kualitas gizi.
- **Resep kurang fleksibel:** banyak aplikasi resep mengharuskan pengguna membeli bahan baru yang mahal atau tidak sesuai dengan kebiasaan masak lokal.

### Target Pengguna

- Mahasiswa dan anak kos yang membutuhkan menu bergizi dengan anggaran terbatas.
- Keluarga muda yang ingin mengoptimalkan pengeluaran dapur dan isi kulkas.
- Konsumen yang peduli lingkungan dan ingin mengurangi limbah makanan.

### Cara TAKARKUY Membantu

- **Ketika belum berbelanja:** pengguna menentukan budget dan target gizi, lalu TAKARKUY memberi saran bahan belanja serta menu.
- **Ketika sudah berbelanja:** pengguna memindai struk belanja atau memasukkan bahan secara manual, lalu TAKARKUY memanfaatkan stok tersebut untuk membantu pengguna memilih resep dan mencegah bahan terbuang.

## Perbandingan dengan Aplikasi Serupa

| Aspek | Cookpad (Indonesia) | SuperCook (Global) | Mealime (Global) | TAKARKUY |
| --- | --- | --- | --- | --- |
| Fokus utama | Komunitas dan resep | Pencocokan bahan dan resep | Perencanaan menu | Optimasi anggaran dan zero waste |
| Alur utama | Cari resep → beli bahan | Pilih bahan → dapat resep | Pilih menu → shopping list | Input budget → belanja + jadwal masak, atau input stok → pilih resep |
| Konteks bahan Indonesia | Ya | Terbatas | Terbatas | Ya, termasuk bahan dan bumbu lokal |
| Perencanaan anggaran | Tidak | Tidak | Terbatas/premium | Ya, berdasarkan target gizi dan durasi makan |
| Pemindaian bahan/struk | Tidak | Barcode terbatas | Tidak | OCR struk belanja; hasil dapat diedit manual |
| Prioritas bahan kedaluwarsa | Tidak | Tidak | Tidak | Ya, berbasis estimasi masa simpan; cuaca dapat dipertimbangkan untuk bahan sensitif |
| Meal scheduler | Tidak | Tidak | Manual | Jadwal menu untuk 1–7 hari |

## Pembagian Modul dan Cakupan yang Direncanakan

Daftar CRUD dan model yang direncanakan tidak semuanya sudah diimplementasikan; lihat tabel status di atas untuk kemampuan kode saat ini.

### Modul 1 — Smart Budget Meal Planner

**PIC:** Alfredo Nathaniel Putra Harsono

- **Input:** nominal budget, durasi 1–7 hari, jumlah porsi 1–10 orang, waktu makan, target gizi, dan bahan yang dihindari.
- **Output:** kombinasi resep yang diupayakan mendekati budget tanpa melampauinya, daftar belanja per bahan, jadwal menu, serta estimasi kalori, protein, karbohidrat, dan lemak. Pencarian memakai heuristik; tidak menjamin kombinasi optimal global. Pengulangan dibatasi/disebar jika katalog punya alternatif.
- **Batas MVP:** jika data resep untuk satu waktu makan habis karena pantangan, hasil waktu makan lain tetap muncul dengan peringatan. Rekomendasi sebelumnya diingat lewat sesi browser dan resep di tanggal/waktu makan yang sama dihindari saat ada alternatif. Belum mencatat apakah menu benar-benar dimasak.
- **Harga:** snapshot Kabupaten Garut diutamakan; referensi toko daring non-Garut melengkapi bahan yang belum punya harga lokal dan diberi keterangan. Bukan harga real-time. Jika budget jauh melebihi variasi katalog, hasil menunjukkan sisa dana tanpa membesar-besarkan porsi.
- **Pembelian buah:** kebutuhan pisang, jeruk, dan melon digabung untuk seluruh rencana, lalu dibulatkan ke perkiraan buah utuh. Biaya memakai massa beli; gizi memakai bagian termakan. Ukuran/rendemen adalah proksi, bukan minimum pembelian supermarket yang sudah diverifikasi.
- **Target gizi:** tinggi protein dan rendah kalori dapat dipilih bersama; seimbang tidak dapat digabung dengan keduanya. Tinggi protein menetapkan minimum **80 g/orang/hari untuk tiga waktu makan**; satu/dua waktu makan memakai minimum 27/54 g. Rendah kalori memakai batas gabungan waktu makan terpilih: pagi 500, siang 325, malam 325 kkal, atau **1.150 kkal/orang/hari** bila ketiganya dipilih. Syarat diterapkan pada jumlah menu harian, bukan wajib 26 g pada setiap resep. Angka ini adalah parameter simulasi, bukan rekomendasi kebutuhan gizi pribadi.
- **Data saat ini:** model `Recipe`, `RecipeIngredient`, `Ingredient`, dan `IngredientPrice`; riwayat rekomendasi disimpan di sesi browser. `BudgetPlan` dan `ShoppingListItem` masih model yang direncanakan, belum ada pada kode saat ini.
- **Halaman:** 1 halaman dengan form dan hasil dalam satu tampilan, mengikuti mockup terakhir.

**CRUD Smart Budget Meal Planner:**

- **Create:** membuat card rencana dan daftar belanja dari input budget, durasi, jumlah porsi, target gizi, dan preferensi.
- **Read:** menampilkan daftar card dan detail belanja per kategori, estimasi harga, total vs budget, serta jadwal masak.
- **Update:** mengubah judul card, budget, durasi, porsi, atau item belanja; hasil dan total belanja dihitung ulang.
- **Delete:** menghapus satu card rencana beserta item belanjanya.

### Modul 2 — Smart Pantry & Meal Planner

**PIC:** Rajendra Akbar Mahdiansyah

- **Input bahan:** OCR struk melalui **Tesseract.js di browser** atau form manual berisi nama, kategori, jumlah, dan satuan. Lokasi/tanggal kedaluwarsa dapat diisi setelah stok tersimpan; tidak wajib pada input awal. Hasil OCR dapat dikoreksi, ditambah baris, atau dihapus sebelum disimpan.
- **Fallback OCR:** bila confidence Tesseract kurang dari 80%, tidak tersedia, tidak ada item terbaca, atau OCR gagal, foto dikirim ke backend untuk dibaca Gemini jika dikonfigurasi. Foto JPG/PNG/WebP maksimal 10 MB. Jika fallback gagal, pengguna tetap dapat memeriksa hasil awal atau memasukkan bahan manual.
- **Saran nama:** koreksi pribadi → nama/alias katalog → fuzzy matching → Gemini untuk memilih kandidat katalog yang tersedia. Hasil Gemini tidak otomatis menambahkan bahan baru ke katalog global.
- **Virtual Pantry:** saran lokasi dan rentang masa simpan berasal dari tabel lokal `IngredientShelfLife` berbasis referensi FoodKeeper, **bukan tanggal kedaluwarsa yang ditebak Gemini**. Saran awal bisa dikoreksi; gunakan tanggal label kemasan jika tersedia. Integrasi Open-Meteo belum dibuat.
- **Privasi dan batas:** foto serta teks mentah tidak disimpan oleh aplikasi, tetapi foto dikirim ke layanan Google saat fallback foto digunakan. Fallback foto dan pencocokan nama masing-masing dibatasi 10 percobaan per sesi browser per hari; ini bukan pembatas biaya global/akun.
- **Integrasi yang direncanakan:** `pantry_service.kurangi_stok()` untuk aksi **Sudah Masak** Modul 4; belum tersedia.
- **Data yang dipegang:** `PantryItem` dan `PantryNameCorrection`, masih berbasis sesi browser, bukan kepemilikan akun lintas perangkat.
- **Halaman:** 1 halaman berisi dua panel input dan tabel inventaris.

**CRUD Virtual Pantry:**

- **Create:** menambahkan bahan lewat form manual atau hasil OCR struk yang sudah diperiksa dan diedit.
- **Read:** menampilkan tabel stok, lokasi simpan, dan estimasi kedaluwarsa.
- **Update:** mengubah nama, kategori, kuantitas, lokasi simpan, atau estimasi daya simpan. Kuantitas juga berkurang saat **Sudah Masak**.
- **Delete:** menghapus satu bahan dari inventaris.

Foto bahan mentah dan image classification dihapus dari cakupan fitur.

### Modul 3 — User Account & Food Preference

**PIC:** Attar Rais Hakam

- **Landing page untuk guest:** hero, ringkasan masalah, cara kerja, dan CTA daftar. Simulasi kalkulator budget bersifat opsional.
- **Autentikasi saat ini:** register, login, dan logout menggunakan Django Authentication berbasis sesi, bukan JWT atau Google OAuth. Form daftar meminta nama lengkap dan email; email disimpan juga sebagai username otomatis. Login menerima email/username yang memang ada di database, tetapi pendaftaran belum menyediakan username pilihan pengguna.
- **Kata sandi:** disimpan sebagai hash melalui `create_user()`, bukan teks asli. Minimal 8 karakter, mengandung huruf kapital, angka, dan simbol, serta lolos validator bawaan Django. Akun dapat diperiksa melalui `/admin/` oleh superuser.
- **Alur beranda:** setelah daftar/login pengguna menuju `/modul5/`; membuka `/` saat sudah login juga diarahkan ke sana. Tautan kembali ke beranda pada halaman modul mengarah ke Modul 5 untuk pengguna login, dan landing untuk guest.
- **Profil & Preferensi Makanan:** data diri, target diet/gizi, alergi, dan preferensi halal digabung dalam satu halaman. Data ini menjadi acuan perencanaan Modul 1 dan pemilihan resep Modul 4.
- **Data saat ini:** `User` bawaan Django dan sesi. `UserProfile` serta `FoodPreference` masih direncanakan.
- **Halaman:** 4 halaman, yaitu Landing, Register, Login, dan Profil & Preferensi.

**CRUD User Account & Food Preference:**

- **Create:** mendaftarkan akun, lalu mengisi data diri, target diet/gizi, alergi, dan preferensi halal.
- **Read:** menampilkan informasi akun, profil, dan preferensi milik pengguna.
- **Update:** mengubah informasi akun dan data diri yang tersedia di profil, serta target diet/gizi, alergi, dan preferensi halal.
- **Delete:** belum termasuk cakupan fitur untuk akun, profil, maupun preferensi.

Login dan logout merupakan operasi autentikasi.

### Modul 4 — Recipe Book & Cooking Tracker

**PIC:** Alena Aura Deviyana

- **Recipe book:** pencarian dan detail resep, dengan filter bahan cukup di pantry, di bawah harga tertentu, halal, serta prioritas bahan kritis (mendekati estimasi kedaluwarsa).
- **Resep favorit:** pengguna dapat menyimpan dan menghapus resep dari daftar favorit pribadi.
- **Sudah Masak:** memanggil `pantry_service.kurangi_stok()` milik Modul 2 untuk mengurangi bahan yang terpakai.
- **Cooking tracker:** mencatat riwayat masak berupa resep, waktu, dan bahan terpakai.
- **Data yang dipegang:** `Resep`, `FavoritResep`, `CookingHistory`.
- **Halaman:** 1 halaman yang menggabungkan list/detail resep, favorit, dan tracker dalam satu tampilan, mengikuti mockup terakhir.

**CRUD Recipe Book & Cooking Tracker:**

- **Create:** administrator menambahkan resep; pengguna menyimpan resep favorit atau mencatat riwayat setelah aksi **Sudah Masak** berhasil.
- **Read:** pengguna mencari, memfilter, dan membuka detail resep, serta melihat favorit dan riwayat masak pribadi.
- **Update:** administrator mengubah informasi resep. Mengedit favorit atau riwayat masak belum termasuk cakupan fitur.
- **Delete:** administrator menghapus resep dengan tetap menjaga riwayat masak yang sudah tercatat; pengguna menghapus resep dari favorit. Menghapus riwayat masak belum termasuk cakupan fitur.

### Modul 5 — Eco-Savings & Market Locator

**PIC:** Aiko Zahwa

- **Statistik:** total dihemat dan limbah dicegah ditampilkan sebagai card di Dashboard.
- **Market locator:** peta pasar tradisional dan bank sampah ditampilkan dalam modal/popup yang dibuka melalui tombol di Dashboard.
- **Data yang dipegang:** agregasi **read-only** dari Modul 1, 2, dan 4; tidak memiliki model utama sendiri.
- **Halaman:** 0 halaman mandiri; seluruh fitur terintegrasi ke Dashboard.

**CRUD Eco-Savings & Market Locator:**

- **Create:** tidak ada; modul ini tidak menyimpan data utama sendiri.
- **Read:** menampilkan card total dihemat dan limbah dicegah di Dashboard, serta peta pasar/bank sampah melalui modal.
- **Update:** tidak ada; statistik dihitung dari data Modul 1, 2, dan 4.
- **Delete:** tidak ada; penghapusan data dilakukan pada modul sumbernya.

## Integrasi Antar Modul yang Direncanakan

Integrasi profil, stok ke planner, aksi **Sudah Masak**, dan agregasi statistik berikut belum selesai. Alur aktif saat ini adalah autentikasi → beranda Modul 5 → navigasi ke halaman modul; daftar belanja tidak otomatis menambah stok.

1. **Modul 3 → Modul 1 dan 4:** target diet/gizi, alergi, dan preferensi halal menjadi acuan perencanaan serta pemilihan resep.
2. **Modul 1 → Modul 2:** setelah berbelanja, pengguna memasukkan stok melalui OCR struk atau input manual. Daftar belanja tidak otomatis dianggap sebagai stok pantry.
3. **Modul 2 → Modul 4:** stok dan estimasi kedaluwarsa digunakan untuk filter ketersediaan bahan dan prioritas bahan kritis.
4. **Modul 4 → Modul 2:** aksi **Sudah Masak** memanggil `pantry_service.kurangi_stok()` berdasarkan bahan terpakai, lalu mencatat `CookingHistory`. Pengurangan stok dan pencatatan riwayat harus berhasil bersama agar data tetap konsisten.
5. **Modul 1, 2, dan 4 → Modul 5:** data rencana belanja, stok, dan riwayat masak menjadi sumber agregasi statistik di Dashboard.

## Ringkasan Halaman yang Direncanakan

| Modul | Halaman / Tampilan | Jumlah Halaman Mandiri |
| --- | --- | --- |
| 1 | Form budget dan hasil perencanaan dalam satu tampilan. | 1 |
| 2 | Dua panel input bahan dan tabel inventaris. | 1 |
| 3 | Landing, Register, Login, serta Profil & Preferensi. | 4 |
| 4 | List/detail resep, favorit, dan cooking tracker dalam satu tampilan. | 1 |
| 5 | Card statistik di Dashboard dan modal/popup market locator. | 0 |

Hitungan di atas adalah rencana tampilan, bukan jumlah halaman yang sudah selesai. Dalam kode saat ini, `/modul5/` adalah beranda mandiri setelah login; `/modul4/` masih template kosong dan halaman profil belum tersedia. Market locator masih direncanakan sebagai modal/popup.

## API dan Sumber Data

Planner memakai katalog lokal yang telah diimpor, bukan memanggil API resep/gizi/harga setiap kali pengguna menghitung menu. API pengumpulan dataset dipakai oleh skrip terpisah; kandidat harus dikurasi sebelum aktif.

| API / Sumber | Pemakaian saat ini |
| --- | --- |
| Gemini API | Fallback pembacaan foto struk dan pencocokan nama ke kandidat katalog melalui backend. Opsional; key hanya berada di server. |
| [TheMealDB API](https://www.themealdb.com/docs_api_guide.php) | Mengumpulkan kandidat resep melalui `data/fetch_themealdb.py` dan `data/fetch_themealdb_candidates.py`; bukan runtime planner. |
| Open Food Facts API | Mengumpulkan kandidat produk melalui `data/fetch_openfoodfacts_products.py`; belum otomatis menjadi stok atau bahan aktif. |
| Bapanas, TKPI, USDA SR Legacy | Snapshot/arsip komposisi bahan untuk gizi. Sebagian memakai estimasi/proksi yang diberi status; PDF TKPI lokal belum diekstrak ke katalog. USDA FoodData Central API tidak dipanggil runtime. |
| Bapokting Garut, PIHPS, referensi toko daring | Snapshot harga dan pelengkap non-Garut, bukan harga supermarket real-time. |
| Kaggle dan Mendeley Data | Sumber kandidat resep/bahan untuk kurasi; tidak semua kandidat lengkap atau layak planner. |
| USDA FoodKeeper melalui mirror historis | Acuan lokal rentang masa simpan berdasarkan kondisi penyimpanan; bukan jaminan keamanan atau tanggal label kemasan. |
| [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | Direncanakan untuk cuaca; belum terintegrasi. |
| [OpenStreetMap](https://www.openstreetmap.org/) — Nominatim dan Overpass | Direncanakan untuk market locator; belum terintegrasi. |

Tautan sumber, status verifikasi, lisensi, dan asumsi setiap kelompok data dicatat di [data/README.md](data/README.md) dan [data/DATASETS.md](data/DATASETS.md). `raw/` menyimpan sumber, `processed/` dan `mapping/` membangun katalog, sedangkan `scratch/` serta `staging/` menyimpan kandidat/audit. Folder kandidat bukan data runtime dan tidak boleh dihapus hanya karena belum aktif.

## Teknologi dan Data Pendukung

| Teknologi / Data | Kegunaan di TAKARKUY |
| --- | --- |
| [Tesseract.js](https://github.com/naptha/tesseract.js) | OCR untuk membaca teks pada foto struk belanja. Hasilnya dapat diedit manual di tabel sebelum disimpan ke pantry. Tesseract.js dijalankan sebagai library, bukan Public API. |
| Django 5.2, Django Authentication, Django Admin | Backend, autentikasi sesi, validasi, dan pengelolaan akun oleh administrator. |
| SQLite / PostgreSQL | SQLite untuk lokal; PostgreSQL ketika `PRODUCTION=True`. |
| WhiteNoise / Gunicorn | Static files dan server deployment. |

## Menjalankan Secara Lokal

Jalankan dari akar proyek dengan Python yang kompatibel dengan Django 5.2 (minimal 3.10):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py import_catalog data/fixtures/catalog_seed.json --sync-generated-relations
python manage.py runserver
```

Untuk database yang sudah berisi data, cadangkan dulu sebelum impor. Opsi `--sync-generated-relations` hanya menyinkronkan relasi bahan/tag buatan generator pada resep dalam fixture; gunakan **fixture lengkap**, bukan potongan. Stok pantry, relasi bersumber pengguna, dan resep di luar fixture dipertahankan. Impor katalog bukan bagian dari setiap request aplikasi.

| URL lokal | Tampilan |
| --- | --- |
| `http://127.0.0.1:8000/` | Landing untuk guest; redirect ke Modul 5 setelah login. |
| `/signup/`, `/login/` | Daftar dan masuk akun. |
| `/modul1/` | Simulasi Meal Plan. |
| `/modul2/` | Smart Pantry dan input struk/manual. |
| `/modul4/` | Template Recipe Book; isi utama masih kosong. |
| `/modul5/` | Beranda dengan header navigasi; wajib login. |
| `/admin/` | Django Admin; wajib akun staff/superuser. |

Modul 1, 2, dan template Modul 4 saat ini masih dapat diakses guest. Untuk membuat akun administrator lokal:

```bash
python manage.py createsuperuser
```

### Environment

`config/settings.py` membaca `.env` melalui `python-dotenv`. Untuk lokal cukup `PRODUCTION=False`; konfigurasi Gemini berikut **opsional**:

```dotenv
PRODUCTION=False
PANTRY_LLM_PROVIDER=gemini
PANTRY_LLM_MODEL=gemini-2.5-flash-lite
GEMINI_API_KEY=isi_key_pribadi_anda
```

Nilai key di atas hanya placeholder. `.env` dan `db.sqlite3` sudah diabaikan Git; jangan menaruh API key atau password database di file lain yang akan di-commit. Tanpa provider/key Gemini, OCR Tesseract, input manual, serta pencocokan nama lokal tetap dapat dipakai. Browser membutuhkan akses jaringan untuk memuat aset/model Tesseract; backend membutuhkan jaringan ketika memanggil Gemini.

### Pembaruan Dataset dan Tes

Build ulang dari snapshot lokal dan validasi sebelum impor:

```bash
python data/build_candidate_indexes.py
python data/build_final.py
python data/validate_candidates.py
python data/validate_catalog.py
```

Build memerlukan snapshot/arsip sumber yang tersedia di `data/raw/` dan `data/scratch/`. Pengambilan ulang API tidak berjalan otomatis; lihat dokumentasi dataset sebelum memperbarui snapshot.

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
node --test apps/pantry/tests_js/receipt_parser.test.mjs
```

Tes parser JavaScript memerlukan Node.js. Audit 1 Oktober 2026 meloloskan **106 tes Django dan 9 tes JavaScript**; tes Gemini memakai respons mock, bukan membuktikan key, kuota, atau akurasi API live. Perapian Python memakai aturan `ruff.toml`; Ruff adalah alat pengembangan opsional, bukan dependensi runtime.

## Catatan Deployment PWS

- Atur environment PWS terpisah dari `.env` lokal: `PRODUCTION=True`, `DJANGO_SECRET_KEY` yang kuat, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, serta `SCHEMA` sesuai schema yang diberikan. Variabel Gemini opsional sama seperti contoh lokal.
- `PRODUCTION=True` memakai PostgreSQL dan cookie secure; gunakan domain HTTPS yang sudah diizinkan dalam `config/settings.py`. Jangan menggunakan konfigurasi produksi untuk akses HTTP lokal.
- Jalankan `python manage.py migrate --noinput` sebelum impor fixture terbaru, termasuk migrasi `catalog.0002_ingredient_calories_method_text` agar catatan sumber gizi panjang diterima PostgreSQL.
- Jalankan `python manage.py collectstatic --noinput` dalam alur deployment. Untuk memperbarui katalog, cadangkan database dan gunakan perintah impor fixture lengkap di atas.
- Audit lokal belum memverifikasi PWS, koneksi database produksi, atau Gemini live. Pemeriksaan produksi menemukan peringatan HSTS/pengalihan HTTPS; periksa konfigurasi reverse proxy PWS sebelum mengaktifkannya di Django agar tidak menimbulkan redirect loop.
- Jangan menghapus database/schema sebagai langkah pertama saat deployment gagal. Periksa log aplikasi dan migrasi; reset schema dapat menghapus seluruh akun dan stok pada schema tersebut.

## Peran Pengguna yang Direncanakan

Hak akses berikut adalah target produk. Saat ini Modul 1/2 dapat dipakai guest, stok masih berbasis sesi, Modul 5 wajib login, dan Django Admin tersedia untuk akun staff dengan izin yang sesuai. Pengelolaan master katalog dilakukan melalui command impor; CRUD katalog di Django Admin belum didaftarkan.

| Peran | Hak Akses |
| --- | --- |
| Guest | Mengakses landing page dan informasi fitur, serta register/login. Simulasi kalkulator budget bersifat opsional. |
| Registered User | Mengelola budget planner, daftar belanja, Virtual Pantry melalui OCR struk atau input manual, profil dan preferensi, serta resep favorit; melihat resep dan riwayat masak, mencatat **Sudah Masak**, serta mengakses Dashboard dan modal market locator. |
| Administrator | Mengelola master bahan, harga referensi, serta database resep masakan Indonesia. |

## Deployment dan Desain

- **PWS:** [https://alfredo-nathaniel-takarkuy.pws.cs.ui.ac.id](https://alfredo-nathaniel-takarkuy.pws.cs.ui.ac.id)
- **Figma:** [Desain TAKARKUY](https://www.figma.com/design/GbnAebmRymsFjgLebkKmUJ/PBPUY?node-id=0-1&t=6YqR0aO6YTlJA2SH-1)
