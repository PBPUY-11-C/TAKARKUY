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

### Modul 2 — Smart Pantry & Meal Planner

**PIC:** Rajendra Akbar Mahdiansyah

- **Input bahan:** hanya melalui OCR struk belanja menggunakan **Tesseract.js** (hasil dapat diedit manual di tabel sebelum disimpan) dan form input manual berisi nama, kategori, kuantitas, lokasi simpan, serta estimasi daya simpan.
- **Virtual Pantry:** menampilkan daftar stok beserta estimasi kedaluwarsa. Cuaca dari Open-Meteo dapat dipertimbangkan untuk bahan yang sensitif.
- **Integrasi:** menyediakan fungsi `pantry_service.kurangi_stok()` untuk dipanggil Modul 4 saat pengguna menekan **Sudah Masak**.
- **Data yang dipegang:** `PantryItem`.
- **Halaman:** 1 halaman berisi dua panel input dan tabel inventaris.

Foto bahan mentah dan image classification dihapus dari cakupan fitur.

### Modul 3 — User Account & Food Preference

**PIC:** Attar Rais Hakam

- **Landing page untuk guest:** hero, ringkasan masalah, cara kerja, dan CTA daftar. Simulasi kalkulator budget bersifat opsional.
- **Autentikasi:** register, login, dan logout.
- **Profil & Preferensi Makanan:** data diri, target diet/gizi, alergi, dan preferensi halal digabung dalam satu halaman. Data ini menjadi acuan perencanaan Modul 1 dan pemilihan resep Modul 4.
- **Data yang dipegang:** `User`, `UserProfile`, `FoodPreference`.
- **Halaman:** 4 halaman, yaitu Landing, Register, Login, dan Profil & Preferensi.

### Modul 4 — Recipe Book & Cooking Tracker

**PIC:** Alena Aura Deviyana

- **Recipe book:** pencarian dan detail resep, dengan filter bahan cukup di pantry, di bawah harga tertentu, halal, serta prioritas bahan kritis (mendekati estimasi kedaluwarsa).
- **Resep favorit:** pengguna dapat menyimpan dan menghapus resep dari daftar favorit pribadi.
- **Sudah Masak:** memanggil `pantry_service.kurangi_stok()` milik Modul 2 untuk mengurangi bahan yang terpakai.
- **Cooking tracker:** mencatat riwayat masak berupa resep, waktu, dan bahan terpakai.
- **Data yang dipegang:** `Resep`, `FavoritResep`, `CookingHistory`.
- **Halaman:** 1 halaman yang menggabungkan list/detail resep, favorit, dan tracker dalam satu tampilan, mengikuti mockup terakhir.

### Modul 5 — Eco-Savings & Market Locator

**PIC:** Aiko Zahwa

- **Statistik:** total dihemat dan limbah dicegah ditampilkan sebagai card di Dashboard.
- **Market locator:** peta pasar tradisional dan bank sampah ditampilkan dalam modal/popup yang dibuka melalui tombol di Dashboard.
- **Data yang dipegang:** agregasi **read-only** dari Modul 1, 2, dan 4; tidak memiliki model utama sendiri.
- **Halaman:** 0 halaman mandiri; seluruh fitur terintegrasi ke Dashboard.

## Rancangan CRUD

Tabel berikut menjelaskan rencana operasi **Create, Read, Update, Delete** untuk setiap model, bukan status implementasi. Data pribadi dikelola oleh pemiliknya, sedangkan master resep dikelola administrator. Tanda **—** berarti operasi tersebut tidak termasuk cakupan fitur.

| Modul / Model | Create | Read | Update | Delete |
| --- | --- | --- | --- | --- |
| 1 — `BudgetPlan` | Membuat rencana dari budget, durasi, porsi, dan preferensi. | Melihat rencana, total belanja vs budget, dan jadwal masak. | Mengubah input dan menghitung ulang rencana. | Menghapus rencana beserta item belanjanya. |
| 1 — `ShoppingListItem` | Menambahkan item belanja ke rencana. | Melihat item per kategori beserta kuantitas dan estimasi harga. | Mengubah item atau kuantitas dan menghitung ulang total belanja. | Menghapus item dari daftar belanja. |
| 2 — `PantryItem` | Menambahkan stok dari hasil OCR yang dikonfirmasi atau form manual. | Melihat inventaris dan estimasi kedaluwarsa. | Mengubah data bahan, kuantitas, lokasi simpan, atau estimasi daya simpan; mengurangi stok melalui `kurangi_stok()`. | Menghapus bahan dari inventaris. |
| 3 — `User` | Mendaftarkan akun. | Membaca informasi akun sendiri. | Memperbarui data akun yang tersedia di halaman profil. | — |
| 3 — `UserProfile` | Mengisi profil pengguna. | Melihat profil sendiri. | Mengubah data diri. | — |
| 3 — `FoodPreference` | Menyimpan target diet/gizi, alergi, dan preferensi halal. | Melihat preferensi untuk profil, perencanaan, dan pemilihan resep. | Mengubah target dan preferensi, termasuk menghapus pilihan alergi. | — |
| 4 — `Resep` | Administrator menambahkan master resep. | Pengguna mencari, memfilter, dan melihat detail resep. | Administrator memperbarui master resep. | Administrator menghapus master resep dengan menjaga riwayat masak yang sudah tercatat. |
| 4 — `FavoritResep` | Menyimpan resep ke favorit pribadi. | Melihat daftar favorit. | — | Menghapus resep dari favorit pribadi. |
| 4 — `CookingHistory` | Mencatat resep, waktu, dan bahan terpakai saat **Sudah Masak** berhasil. | Melihat riwayat masak pribadi. | — | — |
| 5 — Agregasi Dashboard | — | Melihat total dihemat, limbah dicegah, serta peta pasar/bank sampah melalui modal. | — | — |

Login dan logout merupakan operasi autentikasi. Riwayat masak dibuat melalui aksi **Sudah Masak** dan hanya dibaca melalui tracker; edit atau hapus riwayat belum masuk cakupan. Modul 5 membaca data sumber tanpa menyediakan CRUD tersendiri.

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
