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
| Meal scheduler | Tidak | Tidak | Manual | Jadwal masak untuk 1–7 hari |

## Pembagian Modul

### Modul 1 — Smart Budget Meal Planner

**PIC:** Alfredo Nathaniel Putra Harsono

- **Input:** budget, durasi 1–7 hari, porsi 1–10, waktu makan (pagi/siang/malam), target gizi (seimbang, tinggi protein, rendah kalori), pilihan nasi, dan bahan yang dihindari. Alergi diambil dari profil (Modul 3).
- **Output:** jadwal menu per hari, daftar belanja per kategori dengan estimasi harga, total belanja dibanding budget, dan estimasi gizi harian. Stok Pantry dipakai lebih dulu sehingga belanja bisa lebih kecil.
- **Data yang dipegang:** `BudgetPlan`, `PlannedMeal`, `ShoppingListItem`, `PlanPreview`.
- **Halaman:** 1 halaman berisi form dan hasil, plus daftar Rencana Saya.

**CRUD Smart Budget Meal Planner:**

- **Create:** membuat rencana dari input di atas; hasilnya menjadi draft lalu disimpan ke Rencana Saya dengan judul dan tanggal mulai.
- **Read:** melihat daftar Rencana Saya dan detailnya: jadwal, daftar belanja, total vs budget, dan gizi.
- **Update:** mengubah judul/tanggal, mengubah parameter lewat pratinjau, mencari susunan menu lain, atau mengganti satu menu. Total dihitung ulang dan tetap dalam budget.
- **Delete:** menghapus satu rencana beserta jadwal dan daftar belanjanya.

### Modul 2 — Smart Pantry

**PIC:** Rajendra Akbar Mahdiansyah

- **Input bahan:** foto struk dibaca dengan Tesseract.js (Gemini sebagai cadangan bila hasilnya kurang yakin) atau input manual; hasil selalu bisa diperiksa dan diedit sebelum disimpan. Belanjaan dari daftar belanja Modul 1 juga bisa langsung dimasukkan.
- **Virtual Pantry:** tabel stok dengan filter (segera dipakai, kulkas, freezer, suhu ruang) dan perkiraan kedaluwarsa dari acuan masa simpan.
- **Integrasi:** `execute_consumption()` mengurangi stok saat **Sudah Masak** di Modul 4, memakai bahan yang paling cepat kedaluwarsa lebih dulu.
- **Data yang dipegang:** `PantryItem`, `PantryMovement`, `PantryOperation`, `ShelfLifeEstimate`.
- **Halaman:** 1 halaman berisi panel pindai struk, input manual, dan tabel stok.

**CRUD Smart Pantry:**

- **Create:** menambah bahan dari struk, input manual, atau daftar belanja.
- **Read:** melihat stok, lokasi simpan, perkiraan kedaluwarsa, dan riwayat perubahan per bahan.
- **Update:** mengubah nama, jumlah, satuan, kategori, lokasi, dan tanggal. Jumlah juga berkurang otomatis saat **Sudah Masak**.
- **Delete:** menghapus (mengarsipkan) satu bahan; riwayatnya tetap tercatat.

### Modul 3 — User Account & Food Preference

**PIC:** Attar Rais Hakam

- **Landing page:** hero, cara kerja, fitur, dan FAQ untuk guest.
- **Autentikasi:** daftar, masuk (username atau email), dan keluar.
- **Profil & Preferensi:** nama, username, email, ganti kata sandi, target gizi, waktu makan, porsi, alergi, dan bahan yang dihindari. Data ini menjadi nilai awal Modul 1 dan penyaring resep Modul 4.
- **Data yang dipegang:** `User`, `UserProfile`, `FoodPreference`.
- **Halaman:** Landing, Daftar, Masuk, serta Profil & Preferensi.

**CRUD User Account & Food Preference:**

- **Create:** mendaftarkan akun; profil dibuat otomatis.
- **Read:** melihat informasi akun dan preferensi.
- **Update:** mengubah data akun, kata sandi, dan preferensi makanan.
- **Delete:** belum termasuk cakupan.

### Modul 4 — Recipe Book & Cooking Tracker

**PIC:** Alena Aura Deviyana

- **Recipe book:** cari resep dengan filter waktu makan, stok di Pantry, harga, dan favorit. Detail berisi bahan, gizi, estimasi harga, dan cara memasak.
- **Sudah Masak:** pratinjau pemakaian stok lalu konfirmasi; stok dikurangi lewat Modul 2 dan riwayat masak tercatat bersamaan.
- **Integrasi rencana:** menu dari jadwal Modul 1 bisa dibuka, dimasak, atau dilewati.
- **Data yang dipegang:** `RecipeFavorite`, `CookingHistory`.
- **Halaman:** 1 halaman berisi daftar resep, detail resep, favorit, dan riwayat masak.

**CRUD Recipe Book & Cooking Tracker:**

- **Create:** menyimpan favorit dan mencatat riwayat lewat **Sudah Masak**. Resep ditambahkan administrator.
- **Read:** mencari dan melihat resep, favorit, dan riwayat masak.
- **Update:** administrator mengubah resep; pengguna menandai menu rencana sebagai dilewati atau membatalkannya.
- **Delete:** menghapus favorit. Administrator menghapus resep tanpa menghapus riwayat masak.

### Modul 5 — Dashboard, Ulasan & Market Locator

**PIC:** Aiko Zahwa

- **Dashboard:** kalender menu 7 hari, sisa budget per rencana, bahan yang segera harus dipakai, dan masakan terakhir.
- **Ulasan resep:** rating 1–5 dan komentar di detail resep, setelah pernah memasak resep itu.
- **Market locator:** peta dan daftar pasar serta bank sampah dalam popup dari Dashboard.
- **Data yang dipegang:** `RecipeReview`, serta cache dan kuota pencarian peta. Ringkasan Dashboard dibaca dari Modul 1, 2, dan 4.
- **Halaman:** Dashboard sebagai beranda setelah masuk; peta berupa popup.

**CRUD Dashboard, Ulasan & Market Locator:**

- **Create:** menulis ulasan setelah memasak.
- **Read:** melihat ringkasan Dashboard, ulasan resep, dan peta pasar/bank sampah.
- **Update:** mengubah ulasan sendiri.
- **Delete:** menghapus ulasan sendiri; administrator dapat menyembunyikan ulasan.

## Integrasi Antar Modul

1. **Modul 3 → Modul 1 dan 4:** target gizi, waktu makan, porsi, alergi, dan bahan yang dihindari menjadi acuan perencanaan serta penyaringan resep.
2. **Modul 1 → Modul 2:** setelah berbelanja, bahan di daftar belanja bisa dimasukkan ke Pantry; stok Pantry juga dipakai lebih dulu saat menyusun rencana.
3. **Modul 2 → Modul 4:** stok dan perkiraan kedaluwarsa dipakai untuk filter ketersediaan bahan dan prioritas bahan yang segera dipakai.
4. **Modul 4 → Modul 2:** **Sudah Masak** memanggil `execute_consumption()` lalu mencatat `CookingHistory` dalam satu transaksi agar stok dan riwayat tetap konsisten.
5. **Modul 1, 2, dan 4 → Modul 5:** rencana, stok, dan riwayat masak menjadi sumber ringkasan di Dashboard.

## Ringkasan Halaman

| Modul | Halaman / Tampilan | Jumlah Halaman Mandiri |
| --- | --- | --- |
| 1 | Form dan hasil rencana, plus Rencana Saya. | 1 |
| 2 | Panel pindai struk, input manual, dan tabel stok. | 1 |
| 3 | Landing, Daftar, Masuk, serta Profil & Preferensi. | 4 |
| 4 | Daftar resep, detail resep, favorit, dan riwayat masak. | 1 |
| 5 | Dashboard (beranda setelah masuk) dan popup peta. | 1 |

Total aplikasi **8 halaman**. Market locator berupa popup di Dashboard, bukan halaman tersendiri.

## Public API

| API | Kegunaan di TAKARKUY |
| --- | --- |
| [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | Mendukung pertimbangan cuaca dalam estimasi masa simpan bahan sensitif di Virtual Pantry. |
| [USDA FoodData Central API](https://fdc.nal.usda.gov/api-guide) | Mengambil data gizi generik, seperti kalori, protein, dan serat, untuk bahan mentah sebagai acuan Smart Budget Meal Planner. API key disimpan sebagai environment variable. |
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

## Status Integrasi

Seluruh modul memakai view aslinya dan wajib login. Landing, daftar/masuk, dan kalkulator pembagian budget tetap publik. Setelah daftar/masuk, pengguna diarahkan ke planner. Profil menggunakan chip preferensi dan pencarian bahan (maksimal 10 pilihan). Ganti sandi dibatasi 5 percobaan per akun dan 30 per IP dalam jendela 15 menit.

Jalankan `python manage.py migrate --noinput` untuk menerapkan pemisahan `FoodPreference` tanpa menghapus data preferensi lama, lalu `python manage.py collectstatic --noinput` saat deployment.

Planner wajib login, termasuk alias `/modul1/`. Guest hanya dapat membuka landing, daftar/masuk, serta kalkulator pembagian budget di landing; akses planner diarahkan ke `/login/?next=...`.
