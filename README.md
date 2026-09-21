# TAKARKUY

**TAKARKUY** (Tata Kelola Anggaran dan Resep, Kuy!) adalah aplikasi web khusus untuk membantu pengguna merencanakan menu makanan yang sehat, hemat, dan minim limbah makanan. Berbeda dari aplikasi resep konvensional, TAKARKUY memulai perencanaan dari anggaran dan stok bahan yang sudah tersedia, kemudian menyusun rekomendasi menu untuk hari-hari selanjutnya.

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
| Meal scheduler | Tidak | Tidak | Manual | Jadwal masak untuk 3, 5, atau 7 hari |

## Pembagian Modul

### Modul 1 — Smart Budget Meal Planner

**PIC:** Alfredo Nathaniel Putra Harsono

- **Input:** nominal budget, durasi **3/5/7 hari**, jumlah porsi, serta target gizi dan preferensi makanan yang diambil dari Modul 3.
- **Output:** daftar belanja per kategori (protein, sayur, karbo) dengan estimasi harga per item, perbandingan total belanja dengan budget, dan jadwal masak per hari.
- **Data yang dipegang:** `BudgetPlan`, `ShoppingListItem`.
- **Halaman:** 1 halaman dengan form dan hasil dalam satu tampilan, mengikuti mockup terakhir.

**CRUD Smart Budget Meal Planner:**

- **Create:** membuat card rencana dan daftar belanja dari input budget, durasi, jumlah porsi, target gizi, dan preferensi.
- **Read:** menampilkan daftar card dan detail belanja per kategori, estimasi harga, total vs budget, serta jadwal masak.
- **Update:** mengubah judul card, budget, durasi, porsi, atau item belanja; hasil dan total belanja dihitung ulang.
- **Delete:** menghapus satu card rencana beserta item belanjanya.

### Modul 2 — Smart Pantry & Meal Planner

**PIC:** Rajendra Akbar Mahdiansyah

- **Input bahan:** hanya melalui OCR struk belanja menggunakan **Tesseract.js** (hasil dapat diedit manual di tabel sebelum disimpan) dan form input manual berisi nama, kategori, kuantitas, lokasi simpan, serta estimasi daya simpan.
- **Virtual Pantry:** menampilkan daftar stok beserta estimasi kedaluwarsa. Cuaca dari Open-Meteo dapat dipertimbangkan untuk bahan yang sensitif.
- **Integrasi:** menyediakan fungsi `pantry_service.kurangi_stok()` untuk dipanggil Modul 4 saat pengguna menekan **Sudah Masak**.
- **Data yang dipegang:** `PantryItem`.
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
- **Autentikasi:** register, login, dan logout.
- **Profil & Preferensi Makanan:** data diri, target diet/gizi, alergi, dan preferensi halal digabung dalam satu halaman. Data ini menjadi acuan perencanaan Modul 1 dan pemilihan resep Modul 4.
- **Data yang dipegang:** `User`, `UserProfile`, `FoodPreference`.
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

## Integrasi Antar Modul

1. **Modul 3 → Modul 1 dan 4:** target diet/gizi, alergi, dan preferensi halal menjadi acuan perencanaan serta pemilihan resep.
2. **Modul 1 → Modul 2:** setelah berbelanja, pengguna memasukkan stok melalui OCR struk atau input manual. Daftar belanja tidak otomatis dianggap sebagai stok pantry.
3. **Modul 2 → Modul 4:** stok dan estimasi kedaluwarsa digunakan untuk filter ketersediaan bahan dan prioritas bahan kritis.
4. **Modul 4 → Modul 2:** aksi **Sudah Masak** memanggil `pantry_service.kurangi_stok()` berdasarkan bahan terpakai, lalu mencatat `CookingHistory`. Pengurangan stok dan pencatatan riwayat harus berhasil bersama agar data tetap konsisten.
5. **Modul 1, 2, dan 4 → Modul 5:** data rencana belanja, stok, dan riwayat masak menjadi sumber agregasi statistik di Dashboard.

## Ringkasan Halaman

| Modul | Halaman / Tampilan | Jumlah Halaman Mandiri |
| --- | --- | --- |
| 1 | Form budget dan hasil perencanaan dalam satu tampilan. | 1 |
| 2 | Dua panel input bahan dan tabel inventaris. | 1 |
| 3 | Landing, Register, Login, serta Profil & Preferensi. | 4 |
| 4 | List/detail resep, favorit, dan cooking tracker dalam satu tampilan. | 1 |
| 5 | Card statistik di Dashboard dan modal/popup market locator. | 0 |

Total halaman mandiri Modul 1–4 adalah **7 halaman**. Dashboard menjadi halaman bersama di luar hitungan tersebut; bila dihitung sebagai halaman tersendiri, total aplikasi adalah **8 halaman**. Modul 5 tidak menambah halaman mandiri, dan market locator tetap berupa modal/popup.

## Public API

| API | Kegunaan di TAKARKUY |
| --- | --- |
| [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | Mendukung pertimbangan cuaca dalam estimasi masa simpan bahan sensitif di Virtual Pantry. |
| [USDA FoodData Central API](https://fdc.nal.usda.gov/api-guide/) | Mengambil data gizi generik, seperti kalori, protein, dan serat, untuk bahan mentah sebagai acuan Smart Budget Meal Planner. API key disimpan sebagai environment variable. |
| [TheMealDB API](https://www.themealdb.com/docs_api_guide.php) | Menjadi pelengkap variasi resep internasional. Database resep internal tetap menjadi sumber utama karena cakupan resep Indonesia pada API ini terbatas. |
| [OpenStreetMap](https://www.openstreetmap.org/) — Nominatim dan Overpass | Mendukung geocoding serta pencarian pasar tradisional atau bank sampah terdekat. |

## Teknologi dan Data Pendukung

| Teknologi / Data | Kegunaan di TAKARKUY |
| --- | --- |
| [Tesseract.js](https://github.com/naptha/tesseract.js) | OCR untuk membaca teks pada foto struk belanja. Hasilnya dapat diedit manual di tabel sebelum disimpan ke pantry. Tesseract.js dijalankan sebagai library, bukan Public API. |

## Peran Pengguna

| Peran | Hak Akses |
| --- | --- |
| Guest | Mengakses landing page dan informasi fitur, serta register/login. Simulasi kalkulator budget bersifat opsional. |
| Registered User | Mengelola budget planner, daftar belanja, Virtual Pantry melalui OCR struk atau input manual, profil dan preferensi, serta resep favorit; melihat resep dan riwayat masak, mencatat **Sudah Masak**, serta mengakses Dashboard dan modal market locator. |
| Administrator | Mengelola master bahan, harga referensi, serta database resep masakan Indonesia. |

## Deployment dan Desain

- **PWS:** [https://alfredo-nathaniel-takarkuy.pws.cs.ui.ac.id](https://alfredo-nathaniel-takarkuy.pws.cs.ui.ac.id)
- **Figma:** [Desain TAKARKUY](https://www.figma.com/design/GbnAebmRymsFjgLebkKmUJ/PBPUY?node-id=0-1&t=6YqR0aO6YTlJA2SH-1)
