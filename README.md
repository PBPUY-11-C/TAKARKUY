# TAKARKUY

**TAKARKUY** (Tata Kelola Anggaran dan Resep, Kuy!) adalah aplikasi web khusus untuk membantu pengguna merencanakan menu makanan yang sehat, hemat, dan minim limbah makanan. Berbeda dari aplikasi resep konvensional, TAKARKUY memulai perencanaan dari anggaran dan stok bahan yang sudah tersedia, kemudian menyusun rekomendasi menu untuk hari-hari selanjutnya.

## Status Implementasi

Snapshot kode dan inventaris dataset: **6 Oktober 2026**. Harga Garut tetap snapshot **28 September 2026**. Bagian visi, perbandingan, CRUD, dan integrasi di bawah menjelaskan **cakupan/rencana produk**, bukan klaim bahwa seluruh fiturnya sudah selesai.

| Bagian | Sudah tersedia | Belum tersedia |
| --- | --- | --- |
| Modul 1 | Simulasi budget/gizi/pantangan, daftar belanja, trial guest, draft otomatis milik akun, CRUD rencana tersimpan, cari susunan baru, serta ganti satu menu dengan pratinjau biaya dan persetujuan kenaikan budget; slot terhubung ke cooking tracker/dashboard. | Integrasi stok pantry dan edit item belanja secara bebas. |
| Modul 2 | OCR/fallback Gemini dengan kuota akun, cache nama, batch dan ledger stok, CRUD berversi/idempoten, konversi berat, tanggal bersumber, kecocokan resep dan FEFO yang terhubung ke Modul 4. | Pengingat terjadwal dan cuaca. |
| Modul 3 | Landing, username/email, login/logout, profil/preferensi, perubahan password, rate limit database, dan maintenance. | Google OAuth, verifikasi email, serta reset password lewat email. |
| Modul 4 | Recipe Book di `/modul4/`: pencarian/filter, detail/panduan berstatus, favorit pribadi, preview dan pencatatan masak atomik dengan FEFO/ledger, riwayat snapshot, integrasi slot rencana tersimpan. | Foto/durasi terkurasi, resep buatan pengguna, dan undo riwayat. |
| Modul 5 | Dashboard personal: semua rencana aktif hari ini, estimasi sisa budget per rencana, stok prioritas/unknown, riwayat masak, ulasan resep di Modul 4, dan modal peta/daftar kurasi dengan pencarian OSM opsional. | Penghematan/limbah dicegah yang terverifikasi dan cakupan lokasi nasional terkurasi. |

Katalog saat ini berisi **201 bahan, 163 catatan harga, dan 438 resep; 300 resep siap dihitung**, sedangkan 138 masih diblokir. Dari resep siap dihitung, 6 nonaktif sehingga 294 aktif. Fixture tunggal `data/fixtures/catalog_seed.json` berisi **7.140 objek**. Siap dihitung berarti bahan/gizi/harga tersedia untuk simulasi, bukan semua teks cara memasak sudah boleh diterbitkan. Sebanyak 191 resep Mendeley dapat dihitung, tetapi teks langkahnya ditahan untuk review asal/hak pakai. Ada **231 kandidat produk Open Food Facts** dan **1.500 baris kandidat resep** untuk kurasi; sebagian sudah dipromosikan sehingga jangan menjumlahkan kandidat dengan katalog aktif. Rincian sumber, asumsi, dan penghalang ada di [data/DATASETS.md](data/DATASETS.md) dan [review sumber](data/SOURCE_REVIEW.md).

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
- **Output dan budget wajib:** kombinasi resep halal, daftar belanja per bahan, jadwal menu, serta estimasi empat makro. Total belanja **tidak boleh melebihi budget** untuk diterapkan/disimpan; budget tidak dinaikkan otomatis. Hasil infeasible hanya menjelaskan kekurangan biaya, bukan rencana yang dapat disimpan. Sisa budget ditampilkan.
- **Preferensi budget, bukan syarat wajib:** pencarian menargetkan minimal **60% budget** dan biaya satu menu maksimal **2× jatah rata-rata** (`budget / hari / jumlah waktu makan`, untuk seluruh porsi menu). Jika katalog atau target gizi tidak memungkinkan, preferensi dilonggarkan tanpa melonggarkan batas total budget. Pada penggantian manual, pilihan user dapat melewati preferensi per-menu asalkan total dan target gizi tetap memenuhi syarat. Pembelian buah gabungan dapat menurunkan biaya akhir di bawah target 60%. Catatan pelonggaran ditampilkan pada hasil dan pratinjau. Pencarian adalah heuristik dengan maksimal 40 kandidat per waktu makan; bukan jaminan optimum atau pembuktian bahwa seluruh katalog tak mungkin memenuhi preferensi. Total dipilih acak dari biaya yang terjangkau, dengan penalti pengulangan resep/protein.
- **Batas MVP dan riwayat:** jika data resep untuk satu waktu makan habis karena pantangan, hasil waktu makan lain tetap muncul dengan peringatan. Akun membaca riwayat dari `PlannedMeal` miliknya bertanggal hari ini hingga enam hari sebelumnya, termasuk draft dan rencana tersimpan; menu berstatus dilewati tidak dihitung. Berlaku lintas perangkat tanpa tabel riwayat baru. Guest tetap memakai `planner_meal_history` dalam session. Susunan sebelumnya juga menjadi penalti slot saat regenerasi. Ini riwayat jadwal, belum bukti menu benar-benar dimasak.
- **Harga:** snapshot Kabupaten Garut diutamakan; referensi toko daring non-Garut melengkapi bahan yang belum punya harga lokal dan diberi keterangan. Bukan harga real-time. Sisa budget ditampilkan apa adanya tanpa membesar-besarkan porsi.
- **Pembelian buah:** kebutuhan pisang, jeruk, dan melon digabung untuk seluruh rencana, lalu dibulatkan ke perkiraan buah utuh. Biaya memakai massa beli; gizi memakai bagian termakan. Ukuran/rendemen adalah proksi, bukan minimum pembelian supermarket yang sudah diverifikasi.
- **Target gizi:** tinggi protein dan rendah kalori dapat dipilih bersama; seimbang tidak dapat digabung dengan keduanya. Tinggi protein menetapkan minimum **80 g/orang/hari untuk tiga waktu makan**; satu/dua waktu makan memakai minimum 27/54 g. Rendah kalori memakai batas gabungan waktu makan terpilih: pagi 500, siang 325, malam 325 kkal, atau **1.150 kkal/orang/hari** bila ketiganya dipilih. Syarat diterapkan pada jumlah menu harian, bukan wajib 26 g pada setiap resep. Angka ini adalah parameter simulasi, bukan rekomendasi kebutuhan gizi pribadi.
- **Data saat ini:** katalog `Recipe`, `RecipeIngredient`, `Ingredient`, dan `IngredientPrice`; akun memiliki `BudgetPlan` (draft/tersimpan), `PlannedMeal` (jadwal bertanggal), dan `ShoppingListItem`. Snapshot nama, instruksi, gizi, dan belanja dipertahankan agar perubahan katalog tidak diam-diam mengubah rencana yang sudah disimpan. `PlanPreview` menyimpan usulan perubahan selama 15 menit, hanya dapat diterapkan sekali.
- **Alur akun:** generate yang memenuhi budget otomatis menjadi **satu draft terakhir**, bukan langsung menambah rencana permanen. **Simpan Rencana** memasukkannya ke **Rencana Saya**; judul/tanggal mulai bisa diubah dan rencana bisa dihapus. Rencana dapat dibuka di `/modul1/?plan=<id>` oleh pemiliknya dari perangkat lain. Refresh sesudah generate tidak menghitung ulang. Hasil terakhir guest dibawa menjadi draft setelah login/daftar jika akun belum punya draft; draft akun yang sudah ada tidak ditimpa.
- **Perlindungan draft:** perubahan draft wajib membawa versi yang dilihat pengguna. Rencana Baru harus membawa ID/versi draft terakhir serta persetujuan penggantian; request usang ditolak HTTP 409. Perubahan dari rencana tersimpan berbeda ditolak selama ada draft lain: simpan/hapus draft itu dahulu. Preview menyimpan ID dan versi draft untuk mendeteksi penghapusan lalu pembuatan ulang, bukan hanya perubahan nomor versi.
- **Pergantian menu:** **Cari Menu Lain** mencari susunan alternatif dengan parameter yang sama. **Ganti Menu** menetapkan satu slot baru dan mempertahankan kode resep slot lainnya. Backend menghitung ulang seluruh belanja (termasuk pembulatan buah), memeriksa pantangan/target gizi harian, dan menampilkan total sebelum/sesudah serta selisihnya. Jika melewati budget, pengguna harus membatalkan, memilih alternatif, atau secara eksplisit menyetujui budget baru yang cukup. Hasil pencarian tidak menjamin selalu ada alternatif yang memenuhi syarat.
- **Dropdown dan preview:** keduanya memakai `quote_schedule` terhadap seluruh jadwal. Pembelian buah digabung, baru dibulatkan; selisih dropdown sama dengan preview selama katalog/harga tidak berubah di antara request. Alternatif yang melebihi budget atau gagal target gizi tidak ditawarkan. Katalog dimuat sekali per daftar alternatif, bukan sekali per resep.
- **Umur dan kuota preview:** usulan berlaku 15 menit dan hanya sekali pakai. Setiap pembuatan preview membersihkan preview akun tersebut yang kedaluwarsa/terpakai; cron dapat menjalankan `python manage.py cleanup_previews` untuk seluruh akun. Maksimal **20 percobaan hitung preview per akun per jendela 10 menit**, dicatat atomik di database sebelum pencarian. Pencarian gagal tetap dihitung; payload/versi yang ditolak sebelum pencarian tidak dihitung. Logout atau browser lain tidak mereset kuota. API mengembalikan HTTP 429 dan `Retry-After`; waktu jendela dihitung sejak percobaan pertama, bukan sliding window.
- **Penyimpanan efisien:** perubahan judul tidak menulis ulang menu/belanja. Perubahan tanggal hanya memperbarui tanggal jadwal secara batch. Isi anak rencana disinkronkan dengan `bulk_create`/`bulk_update` ketika snapshot/parameter isi berubah; identitas baris yang masih ada dipertahankan. Mengganti resep mengembalikan status slot ke belum masak. Ini belum fitur cooking tracker.
- **Perubahan rencana tersimpan:** perubahan menu/parameter diperlihatkan sebagai pratinjau, lalu diterapkan ke draft. Rencana asal tidak ditimpa sampai pengguna memilih **Simpan Perubahan ke Rencana Asal**; **Simpan Rencana** menyimpan sebagai rencana baru. Versi rencana dan draft diperiksa agar tab/perangkat lama tidak menimpa perubahan baru. API mutasi menggunakan POST, CSRF, dan filter pemilik. Menghasilkan, menyimpan, mengganti, atau menghapus rencana tidak mengubah stok pantry dan belum mencatat aksi memasak.
- **Halaman:** 1 halaman dengan form dan hasil dalam satu tampilan, mengikuti mockup terakhir.

**PR data/produk berikutnya (belum dikerjakan pada perbaikan ini):** hak pakai langkah Mendeley harus dituntaskan menurut `data/SOURCE_REVIEW.md` sebelum publikasi. Panduan alternatif harus ditulis mandiri dari metode memasak yang direview, bukan sekadar parafrase teks yang izinnya belum jelas. Katalog siap hitung saat ini memiliki 36 sarapan; target kurasi berikutnya minimal 80, dengan perluasan kata kunci roti/kentang/ubi/jagung/mie dan sekitar 30 resep kurasi manual. Penambahan tetap memerlukan gram/porsi, padanan bahan, harga, gizi, status halal dan audit sumber. Preferensi akun sudah terhubung ke planner di Modul 3; edit belanja, integrasi stok pantry, serta cooking tracker tetap pekerjaan roadmap modul lanjutan.

**CRUD Smart Budget Meal Planner:**

- **Create:** membuat card rencana dan daftar belanja dari input budget, durasi, jumlah porsi, target gizi, dan preferensi.
- **Read:** menampilkan daftar card dan detail belanja per kategori, estimasi harga, total vs budget, serta jadwal masak.
- **Update:** mengubah judul card, budget, durasi, porsi, atau item belanja; hasil dan total belanja dihitung ulang.
- **Delete:** menghapus satu card rencana beserta item belanjanya.

### Modul 2 — Smart Pantry & Meal Planner

**PIC:** Rajendra Akbar Mahdiansyah

- **Input bahan:** OCR struk melalui **Tesseract.js di browser** atau form manual berisi nama, kategori, jumlah, dan satuan. Keduanya memakai suhu ruang sebagai lokasi awal jika pengguna belum memilih lokasi. Hasil OCR dapat dikoreksi, ditambah baris, atau dihapus sebelum disimpan.
- **Fallback OCR:** bila confidence Tesseract kurang dari 80%, tidak tersedia, tidak ada item terbaca, atau OCR gagal, foto dikirim ke backend untuk dibaca sekaligus dicocokkan katalog dalam satu panggilan Gemini jika dikonfigurasi. Foto JPG/PNG/WebP maksimal 10 MB. Respons memuat raw/name/quantity/unit/kode katalog; kode null/invalid dicocokkan lokal. Jalur foto yang berhasil, kosong, atau gagal **tidak disusul panggilan Gemini teks**; hasil awal/input manual tetap tersedia. Tidak ada kompresi foto seragam yang belum diuji.
- **Saran nama:** koreksi pribadi terkonfirmasi → nama/alias katalog → cache tervalidasi → fuzzy → Gemini untuk maksimal 30 nama dalam satu panggilan teks, masing-masing maksimal lima kandidat. Jalur foto memakai pencocokan lokal saja sesudah pembacaan. Hasil Gemini tidak otomatis menambahkan bahan baru ke katalog global.
- **Virtual Pantry:** saran lokasi dan rentang masa simpan berasal dari tabel lokal `IngredientShelfLife` berbasis referensi FoodKeeper, **bukan tanggal kedaluwarsa yang ditebak Gemini**. Saran awal bisa dikoreksi; gunakan tanggal label kemasan jika tersedia. Integrasi Open-Meteo belum dibuat.
- **Perkiraan otomatis:** input manual/OCR memakai acuan lokal lokasi awal. Tanggal label/manual tidak diubah saat lokasi berubah; tanggal lama yang asalnya tidak diketahui dipertahankan. Estimasi baru tetap dihitung dari tanggal belanja/ditambahkan dan **tidak boleh memperpanjang estimasi sebelumnya**. Jika referensi tidak tersedia, aplikasi tidak mengarang umur simpan. Tidak memakai formula proporsional umur ruangan→freezer tanpa aturan transisi yang tervalidasi. Default suhu ruang bukan anjuran menyimpan bahan mudah rusak di luar kulkas; lihat [panduan FoodSafety.gov](https://www.foodsafety.gov/keep-food-safe/4-steps-to-food-safety).
- **Privasi dan batas:** foto tidak disimpan oleh aplikasi; handler khusus membatasi file/total byte file ke 10 MB dalam memori sebelum CSRF dan tidak memakai temporary upload di disk. Foto tetap dikirim ke Google saat fallback digunakan. Foto dan nama masing-masing maksimal **10 percobaan per akun per hari Jakarta**, dicatat/reservasi atomik di database sebelum API dipanggil, termasuk percobaan gagal. Logout/browser baru tidak meresetnya. Belum ada batas biaya global/per-IP. Request body harus dibatasi juga di reverse proxy; lihat [panduan deploy pantry](docs/PANTRY.md).
- **Cache dan koreksi nama:** cache `NameResolution` v3 memakai fingerprint raw/versi seluruh katalog/provider/model, bukan shortlist, sehingga hasil foto dapat dipakai jalur teks. Kode cache wajib masih ada dan termasuk kandidat lokal; lease 45 detik dilepas ketika request gagal. Jawaban AI/cache diberi label **dengan AI**, tetap perlu diperiksa, dan tidak menjadi alias global. Simpan stok saja tidak membuat koreksi: hanya konfirmasi opsional atau edit nama yang berbeda dan padanan katalog valid yang dicatat. Koreksi pribadi terkonfirmasi menang; koreksi bersama hanya dihitung dari minimal **10 akun aktif berumur 7 hari**, tanpa suara konflik. Koreksi lama yang belum punya bukti konfirmasi tidak dihitung sampai dikonfirmasi ulang. Flag browser tetap bisa dipalsukan, jadi ini bukan bukti interaksi manusia/verifikasi identitas.
- **Pengukuran AI:** `ai_usage` pada respons dan log `pantry_ai_call` berisi status/durasi/token dari metadata provider, tanpa isi struk/API key. Belum ada benchmark struk live atau klaim penghematan persentase. Maksimal satu panggilan adalah kontrak alur scan normal; client jahat masih bisa membuat request baru dan dibatasi kuota akun, bukan flag browser. Validasi Django berbahasa Indonesia. Rincian ada di [docs/PANTRY.md](docs/PANTRY.md).
- **Batch dan audit:** `PantryItem` adalah satu batch pembelian, bukan total gabungan. Migrasi mempertahankan ID, pemilik, kuantitas dan tanggal lama, lalu menulis pergerakan masuk awal. `PantryMovement` menyimpan kuantitas sebelum/sesudah serta snapshot perubahan. Edit memakai version wajib (konflik 409); create/edit/delete memakai UUID `operation_key` yang tetap saat retry. Hapus mengarsipkan batch dan mencatat stok dibuang. Constraint database melarang kuantitas negatif.
- **Konversi dan kecocokan menu:** berat `g/kg`, konversi katalog yang ditinjau (misalnya telur large 50 g/butir), atau berat per unit/pack yang diisi pengguna disimpan sebagai snapshot. **Tidak mengasumsikan 1 ml = 1 g** atau berat bungkus yang tidak diketahui. Stok tanpa padanan katalog/konversi/tanggal yang diketahui, atau tanggal sudah lewat, tidak dihitung sebagai stok resep secara default. Halaman menampilkan hingga 20 menu halal dengan kecocokan bahan per porsi; tidak memanggil AI atau mengurangi stok. Langkah yang ditahan kebijakan publikasi tetap tidak ditampilkan.
- **Layanan integrasi:** `apps.pantry.services.consume_stock(user, requirements, consumption_key)` menerima gram per kode bahan dan mengurangi batch FEFO, tanggal terdekat lalu ID. Satu operasi dapat memakai banyak batch; key unik per akun mencegah konsumsi dua kali. Lock dan ledger ditulis dalam transaksi yang sama, stok kurang membatalkan seluruh operasi. Pecahan unit dibulatkan ke atas maksimal 0,000001 unit dan gram aktual dicatat. Tombol **Sudah Masak** memakai algoritme yang sama melalui `execute_consumption()` dalam transaksi luar dengan `CookingHistory`. Generate/simpan rencana tidak mengurangi stok.
- **Data yang dipegang:** stok, koreksi pribadi, kuota dan operasi milik FK akun. Akun lain tidak dapat membaca atau memutasi ID stok/riwayat tersebut; stok legacy tanpa pemilik tidak diklaim otomatis. `expiry_source` membedakan label/manual/estimate/legacy/unknown. Migrasi 0012 mempertahankan tanggal lama dan menandainya `legacy`, bukan mengarang asalnya sebagai estimasi; stok bertanggal valid dapat dihitung kembali. Cache AI bersama hanya menyimpan nama bahan dan kode kandidat, bukan foto/teks struk lengkap.
- **Halaman:** 1 halaman berisi dua panel input dan tabel inventaris.

**CRUD Virtual Pantry:**

- **Create:** menambahkan bahan lewat form manual atau hasil OCR struk yang sudah diperiksa dan diedit.
- **Read:** menampilkan tabel stok, lokasi simpan, dan estimasi kedaluwarsa.
- **Update:** mengubah nama, kategori, kuantitas/satuan, padanan katalog/berat per unit, lokasi, dan tanggal bersumber; perubahan tercatat sebagai koreksi/perpindahan. **Sudah Masak** di Modul 4 mengurangi batch FEFO dan mencatat gram aktual pada ledger.
- **Delete:** mengarsipkan satu batch dari inventaris, tanpa menghapus ledger-nya.

Foto bahan mentah dan image classification dihapus dari cakupan fitur.

### Modul 3 — User Account & Food Preference

**PIC:** Attar Rais Hakam

- **Landing page untuk guest:** hero, ringkasan masalah, cara kerja, dan CTA daftar. Simulasi kalkulator budget bersifat opsional.
- **Autentikasi:** Django Authentication berbasis sesi, bukan JWT/OAuth. Daftar meminta nama, username (3–30 karakter Latin/ASCII, angka, `_`, `.`, `-`, tanpa `@`), email dan password. Backend `UsernameOrEmailBackend` menerima username tanpa membedakan kapital; input dengan `@` dicari di email, lalu username email akun lama jika tidak ditemukan. Akun lama tidak diubah. Email baru memakai ASCII. Unique expression indexes `lower(username)` dan `lower(email)` diterapkan di PostgreSQL/SQLite; email kosong dikecualikan untuk kompatibilitas akun admin. Migrasi berhenti jika ada duplikat atau username lama bertabrakan dengan email akun lain. Ini bukan janji Unicode case-fold lintas semua collation.
- **Kata sandi:** disimpan sebagai hash melalui `create_user()`, bukan teks asli. Minimal 8 karakter, mengandung huruf kapital, angka, dan simbol, serta lolos validator bawaan Django. Akun dapat diperiksa melalui `/admin/` oleh superuser.
- **Alur beranda:** setelah daftar/login pengguna menuju `/modul5/`; membuka `/` saat sudah login juga diarahkan ke sana. Tautan kembali ke beranda pada halaman modul mengarah ke Modul 5 untuk pengguna login, dan landing untuk guest.
- **Profil & Preferensi:** `/modul3/`, hanya milik akun yang login, menyediakan edit nama/username/email, ganti password, target simulasi makan, waktu makan, porsi dan bahan yang ingin dihindari. Email baru membutuhkan password saat ini. Ganti password menggunakan `PasswordChangeForm` dan `update_session_auth_hash`: sesi perangkat saat ini dipertahankan, sesi perangkat lain dengan hash lama tidak lagi valid. Profil dibuat lazily dengan `get_or_create`, bukan migrasi yang mengubah semua akun. Edit profil memakai versi wajib dan lock akun→profil untuk mencegah tab lama menimpa perubahan. Semua resep planner tetap halal-only menurut kebijakan katalog, bukan sertifikasi; tidak ada toggle untuk membuka resep non-halal.
- **Alergi:** 9 kelompok dipetakan per ID ke 201 bahan (167 review jenis bahan, 34 unknown), bukan pencocokan kata. Bahan unknown dan bumbu minor tak tercatat membuat resep dikecualikan saat ada alergi. Profil mengisi nilai awal rencana baru; input per rencana tidak mengubah profil. Generate, dropdown, preview/regenerate dan penerapan preview memakai gabungan alergi rencana dengan profil terbaru, termasuk pemeriksaan ulang di transaksi penulisan. Snapshot lama tidak diubah; halaman menampilkan peringatan jika tidak sesuai alergi terbaru. Menghapus alergi dari profil tidak menghapus batas yang sudah ada pada rencana lama. Filter bukan jaminan bebas alergen; periksa label dan kontaminasi silang. Pilihan menu bisa sedikit/kosong, khususnya dengan produk olahan yang komposisinya belum ditinjau. Jika slot lain dalam rencana lama juga tidak lolos, Ganti Menu bisa kosong: gunakan Cari Menu Lain/rencana baru. Modul 4 akan memakai helper screening yang sama ketika Recipe Book dibuat.
- **Rate limit bersama:** database `AuthRateBucket`, bukan session/LocMemCache. Per jendela tetap 15 menit: login 10 percobaan per identitas (username/email akun sama berbagi kuota), 100 per IP; signup 5 per email, 30 per IP. Semua percobaan termasuk sukses dihitung; admin login juga dilindungi. Respons 429 memiliki `Retry-After`; logout/perangkat lain tidak mereset. Kunci HMAC tidak menyimpan IP/email asli. Header X-Forwarded-For hanya dipercaya jika REMOTE_ADDR termasuk `AUTH_TRUSTED_PROXY_CIDRS`; rantai dibaca dari kanan hingga hop pertama yang tidak dipercaya. Default daftar proxy kosong. PWS perlu memastikan CIDR proxy aktual sebelum mengaktifkan ini; jika IP yang terlihat hanya IP proxy, batas IP dibagi oleh pengunjung. Limit bukan jaminan melawan botnet/multi-akun dan reset jendela tetap memungkinkan burst di batas waktu.
- **Data:** `User` bawaan Django, sesi, `UserProfile` beserta relasi bahan yang dihindari, dan `AuthRateBucket`.
- **Halaman:** 4 halaman, yaitu Landing, Register, Login, dan Profil & Preferensi.

**CRUD User Account & Food Preference:**

- **Create:** mendaftarkan akun, lalu mengisi data diri, target diet/gizi, alergi, dan preferensi halal.
- **Read:** menampilkan informasi akun, profil, dan preferensi milik pengguna.
- **Update:** mengubah informasi akun, password, target makan/gizi, alergi, porsi, waktu makan, dan bahan yang ingin dihindari. Kebijakan halal planner tetap berlaku untuk semua akun.
- **Delete:** belum termasuk cakupan fitur untuk akun, profil, maupun preferensi.

Login dan logout merupakan operasi autentikasi.

### Modul 4 — Recipe Book & Cooking Tracker

**PIC:** Alena Aura Deviyana

- **Recipe book:** pencarian dan detail resep, dengan filter bahan cukup di pantry, di bawah harga tertentu, halal, serta prioritas bahan kritis (mendekati estimasi kedaluwarsa).
- **Resep favorit:** pengguna dapat menyimpan dan menghapus resep dari daftar favorit pribadi.
- **Sudah Masak:** memanggil `apps.pantry.services.consume_stock()` milik Modul 2 untuk mengurangi bahan yang terpakai.
- **Cooking tracker:** mencatat riwayat masak berupa resep, waktu, dan bahan terpakai.
- **Data yang dipegang:** `Resep`, `FavoritResep`, `CookingHistory`.
- **Halaman:** 1 halaman yang menggabungkan list/detail resep, favorit, dan tracker dalam satu tampilan, mengikuti mockup terakhir.

Implementasi sekarang berada di `apps/recipe_book/` dan **hanya `/modul4/`**. Pencarian nama/bahan, waktu makan, favorit, panduan, alergen dan pantangan disaring di database; filter stok memakai algoritme alokasi yang sama dari satu snapshot inventaris sebelum paginasi. Default hanya menampilkan panduan tersedia. Detail menampilkan estimasi makro dan biaya dari quote daftar belanja planner; tidak mengarang foto, durasi, atau harga yang belum tersedia.

- Endpoint POST JSON: `/modul4/favorite/`, `/modul4/preview/`, `/modul4/cook/`. Semua memerlukan akun/CSRF; stok, favorit, riwayat dan slot hanya milik akun. Preview memakai kuota database bersama planner: 20 upaya per 10 menit.
- `plan_consumption()` adalah simulasi; **bukan reservasi**. Eksekusi membaca ulang batch terkunci dengan urutan FEFO. Batch otomatis boleh berbeda; kekurangan stok atau versi batch manual usang menghasilkan 409. Stok kedaluwarsa tidak dipakai. Tanggal unknown memerlukan persetujuan eksplisit pengguna untuk memeriksa label/kondisi, bukan jaminan keamanan.
- `cook()` mengunci akun → rencana/slot → batch, memakai `PantryOperation` unik dan menulis pengurangan, `PantryMovement.consumed_grams`, `CookingHistory`, status slot dan versi rencana dalam transaksi yang sama. Retry key/payload sama tidak mengurangi dua kali; key berbeda untuk slot yang sudah dimasak tetap ditolak. Riwayat terhubung ke ledger, bukan hanya JSON.
- Kebutuhan stok memakai **massa beli**, gizi memakai massa termakan. Garam, merica dan air ditandai bumbu dasar berdasarkan ID; default tidak dilacak, tetapi bisa disertakan saat konfirmasi. Minyak tidak dikecualikan otomatis. Bahan opsional tetap masuk screening alergi; estimasi gizi resep dapat mencakupnya. Stok tanpa konversi ditampilkan sebagai batch manual: perlu jumlah, berat per unit dan versi; konversi yang sudah diketahui tidak boleh ditimpa.
- Dari jadwal rencana tersimpan, **Lihat Resep** membuka `/modul4/?slot=<id>`. Porsi/versi mengikuti slot; draft harus disimpan dahulu. Memasak menaikkan versi rencana sehingga preview lama ditolak. Ganti satu slot belum dimasak tetap boleh; regenerasi/parameter/porsi diblokir setelah ada slot dimasak. Tanggal mulai boleh berubah tanpa mengubah tanggal riwayat masak. Draft bersumber juga melindungi slot yang sudah dimasak di rencana asal.
- Status panduan: `source_ok`, `authored_reviewed`, `withheld`. Metadata di database terpisah dari fixture lama. Migrasi/import mempertahankan kebijakan publikasi lama non-Mendeley, bukan review hak pakai baru. Mendeley tetap ditahan sampai ada panduan/bukti, catatan dan tanggal tinjauan per resep; snapshot lama tanpa bukti tetap disembunyikan. Impor mempertahankan teks authored yang sudah ditinjau; teks sumber yang berubah perlu review ulang.
- Alergen menambah pilihan `kacang_pohon` dan `sulfit`, **bukan otomatis mereview ulang 201 bahan**. Kemiri/santan/kaldu/minyak yang masih unknown tetap ditutup saat ada alergi. Kelapa tidak otomatis dikelompokkan sebagai kacang pohon; alergi spesifik di luar kelompok perlu memasukkan bahan itu ke pantangan (hard exclusion). Tidak ada jaminan bebas alergen. Recipe Book menjelaskan jumlah yang disembunyikan karena unknown, alergen teridentifikasi dan panduan ditahan, dengan kelompok alasan terpisah.
- `RecipeAllergen` dan `Recipe.allergen_reviewed` diperbarui melalui helper yang sama pada impor dan save/delete bahan penyusun/tag di Admin. Penulisan bulk di luar importer wajib diikuti `python manage.py rebuild_recipe_allergens`; gunakan `--check` untuk mendeteksi drift. Eksekusi tetap memeriksa bahan sebenarnya agar indeks usang tidak meloloskan alergi.
- Favorit resep nonaktif tetap terlihat dengan label tidak tersedia. Riwayat menyimpan snapshot resep/bahan/gizi dan waktu sebenarnya; penghapusan slot/resep menggunakan SET_NULL. Tidak ada undo: koreksi jumlah melalui Smart Pantry tidak menghapus riwayat masak.

**CRUD Recipe Book & Cooking Tracker:**

- **Create:** administrator menambahkan resep; pengguna menyimpan resep favorit atau mencatat riwayat setelah aksi **Sudah Masak** berhasil.
- **Read:** pengguna mencari, memfilter, dan membuka detail resep, serta melihat favorit dan riwayat masak pribadi.
- **Update:** administrator mengubah informasi resep. Mengedit favorit atau riwayat masak belum termasuk cakupan fitur.
- **Delete:** administrator menghapus resep dengan tetap menjaga riwayat masak yang sudah tercatat; pengguna menghapus resep dari favorit. Menghapus riwayat masak belum termasuk cakupan fitur.

### Modul 5 — Eco-Savings & Market Locator

**PIC:** Aiko Zahwa

- **Dashboard:** `/modul5/` menampilkan semua rencana tersimpan aktif hari ini (Asia/Jakarta), estimasi sisa budget terpisah, stok mendekati/melewati tanggal dan tanggal unknown, serta tiga riwayat terbaru. Enam query data; tanpa angka contoh atau klaim penghematan aktual.
- **Ulasan:** rating 1–5 dan komentar maksimal 500 karakter di detail resep Modul 4, hanya setelah riwayat memasak milik akun. Constraint unik, versi/kuota database, moderasi Admin, agregasi rating dan perlindungan email legacy.
- **Market locator:** modal Leaflet/OSM dan daftar kurasi Garut/Depok bersumber. GPS hanya di browser setelah klik. Pencarian wilayah daring opsional (default nonaktif), cache/gate global, tanpa autocomplete; data kurasi tetap berfungsi saat layanan gagal.
- **Data yang dipegang:** dashboard read-only dari Modul 1/2/4; ulasan disimpan di Recipe Book. App dashboard hanya memiliki tabel teknis cache dan kuota, bukan salinan data stok/rencana.
- **Halaman:** seluruh fitur dashboard di `/modul5/`; ulasan di detail `/modul4/`. Kontrak, konfigurasi, sumber dan batas: [docs/DASHBOARD.md](docs/DASHBOARD.md).

**CRUD Eco-Savings & Market Locator:**

- **Create/Update/Delete:** pengguna membuat, mengedit dan menghapus ulasan sendiri setelah memasak; Admin dapat menyembunyikan ulasan. Dashboard tidak mengubah stok/rencana.
- **Read:** ringkasan akun, budget per rencana, stok prioritas, riwayat masak, ulasan publik terlihat, serta peta/daftar pasar dan bank sampah. Penghematan/limbah dicegah belum diklaim.

## Integrasi Antar Modul yang Direncanakan

Integrasi profil ke planner/Recipe Book, **Sudah Masak → pantry/riwayat/slot rencana**, dan agregasi dashboard sudah aktif. Integrasi stok ke perhitungan belanja planner belum selesai; daftar belanja tidak otomatis menambah stok.

1. **Modul 3 → Modul 1/4:** porsi, bahan yang dihindari, dan alergi menjadi acuan planner/Recipe Book; target makan/gizi dan waktu makan juga mengisi planner. Kebijakan halal tetap wajib.
2. **Modul 1 → Modul 2:** setelah berbelanja, pengguna memasukkan stok melalui OCR struk atau input manual. Daftar belanja tidak otomatis dianggap sebagai stok pantry.
3. **Modul 2 → Modul 4:** stok dan estimasi kedaluwarsa digunakan untuk filter ketersediaan bahan dan prioritas bahan kritis.
4. **Modul 4 → Modul 2:** `apps.recipe_book.services.cook()` memakai `execute_consumption()` dan mencatat `CookingHistory` dalam transaksi yang sama. `plan_consumption()` dipakai untuk simulasi dan eksekusi.
5. **Modul 1, 2, dan 4 → Modul 5:** data rencana belanja, stok, dan riwayat masak menjadi sumber agregasi statistik di Dashboard.

## Ringkasan Halaman yang Direncanakan

| Modul | Halaman / Tampilan | Jumlah Halaman Mandiri |
| --- | --- | --- |
| 1 | Form budget dan hasil perencanaan dalam satu tampilan. | 1 |
| 2 | Dua panel input bahan dan tabel inventaris. | 1 |
| 3 | Landing, Register, Login, serta Profil & Preferensi. | 4 |
| 4 | List/detail resep, favorit, dan cooking tracker dalam satu tampilan. | 1 |
| 5 | Card statistik di Dashboard dan modal/popup market locator. | 0 |

Hitungan di atas adalah rencana tampilan, bukan jumlah halaman yang sudah selesai. `/modul5/` adalah beranda setelah login beserta modal market locator, `/modul3/` menyediakan profil/preferensi, dan `/modul4/` menyediakan Recipe Book & Cooking Tracker serta ulasan resep.

## API dan Sumber Data

Planner memakai katalog lokal yang telah diimpor, bukan memanggil API resep/gizi/harga setiap kali pengguna menghitung menu. API pengumpulan dataset dipakai oleh skrip terpisah; kandidat harus dikurasi sebelum aktif.

| API / Sumber | Pemakaian saat ini |
| --- | --- |
| Gemini API | Fallback pembacaan foto struk dan pencocokan nama ke kandidat katalog melalui backend. Opsional; key hanya berada di server. |
| [TheMealDB API](https://www.themealdb.com/docs_api_guide.php) | Mengumpulkan kandidat resep melalui `data/fetch_themealdb.py` dan `data/fetch_themealdb_candidates.py`; bukan runtime planner. |
| Open Food Facts API | Mengumpulkan kandidat produk melalui `data/fetch_openfoodfacts_products.py`; belum otomatis menjadi stok atau bahan aktif. |
| Bapanas, TKPI, USDA SR Legacy | Snapshot/arsip komposisi bahan untuk gizi. Sebagian memakai estimasi/proksi yang diberi status; PDF TKPI lokal belum diekstrak ke katalog. USDA FoodData Central API tidak dipanggil runtime. |
| Bapokting Garut, PIHPS, referensi toko daring | Snapshot harga dan pelengkap non-Garut, bukan harga supermarket real-time. |
| Kaggle dan Mendeley Data | 18 adaptasi Kaggle dan 191 resep Mendeley siap simulasi. Mendeley v3 berlisensi CC BY 4.0; takaran/slot diadaptasi dan teks instruksi ditahan untuk review. Kandidat tidak lengkap tetap diblokir. |
| Sayurbox dan Tokopedia | 20 harga tambahan dalam `mapping/mendeley_sources.json`; melengkapi 44 referensi retail sebelumnya tanpa mengganti harga Garut. Snapshot non-Garut, bukan harga live/ongkir atau pembelian seluruh kemasan. |
| USDA FoodKeeper melalui mirror historis | Acuan lokal rentang masa simpan berdasarkan kondisi penyimpanan; bukan jaminan keamanan atau tanggal label kemasan. |
| [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | Direncanakan untuk cuaca; belum terintegrasi. |
| [OpenStreetMap](https://www.openstreetmap.org/) — Nominatim dan Overpass | Direncanakan untuk market locator; belum terintegrasi. |

Tautan sumber, status verifikasi, lisensi, dan asumsi setiap kelompok data dicatat di [data/README.md](data/README.md) dan [data/DATASETS.md](data/DATASETS.md). `raw/` menyimpan sumber, `processed/` dan `mapping/` membangun katalog, sedangkan `scratch/` serta `staging/` menyimpan kandidat/audit. Folder kandidat bukan data runtime dan tidak boleh dihapus hanya karena belum aktif.

### Struktur folder dan sumber tunggal

| Lokasi | Peran |
| --- | --- |
| `apps/` | Kode, migrasi, tes, template/static per modul; `accounts` = Modul 3, `budget_planner` = Modul 1, `pantry` = Modul 2, `catalog` = master data bersama. |
| `config/`, `templates/` | Konfigurasi Django/URL dan template halaman bersama; Modul 4/5 belum memiliki seluruh fitur final. |
| `data/raw/`, `data/scratch/` | Snapshot/arsip sumber dan kandidat; diperlukan untuk reproduksi/kurasi, bukan junk. |
| `data/mapping/` | Input kurasi: padanan bahan, takaran, nama, sumber, konversi, dan alergen. |
| `data/processed/`, `data/staging/` | Hasil build katalog, laporan audit, dan antrean review. Bukan salinan database pengguna. |
| `data/fixtures/catalog_seed.json` | Satu-satunya fixture katalog: hasil build untuk impor dan tes Django melalui `FIXTURE_DIRS`. Tidak ada salinan di `apps/catalog/fixtures/`. |
| `docs/`, `.github/`, `ruff.toml` | Kontrak implementasi, CI, dan aturan lint; tetap diperlukan. |

`.env`, `db.sqlite3`, `.venv`, cache Python dan `staticfiles/` adalah file lokal/generated yang diabaikan Git; tidak ikut commit. Cleanup fixture tidak menghapus sumber, akun, stok, rencana, atau snapshot pengguna. Menjalankan build tidak lagi membuat salinan fixture aplikasi; validator dan tes menjaga kontrak ini.

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
| `/modul1/` | Simulasi Meal Plan; guest dibatasi 3 rencana berhasil per 24 jam per browser. |
| `/modul2/` | Smart Pantry dan input struk/manual; halaman dan seluruh API wajib login. |
| `/modul4/` | Recipe Book, favorit dan cooking tracker; wajib login, terhubung ke stok dan slot rencana. |
| `/modul5/` | Dashboard personal, ringkasan rencana/stok/masak dan modal peta; wajib login. |
| `/admin/` | Django Admin; wajib akun staff/superuser. |

Guest hanya dapat mengakses Modul 1 dengan batas trial. Modul 2/3/4/5 wajib login. Untuk membuat akun administrator lokal:

```bash
python manage.py createsuperuser
```

### Environment

`config/settings.py` membaca `.env` melalui `python-dotenv`. Untuk lokal cukup `PRODUCTION=False`; konfigurasi Gemini berikut **opsional**:

```dotenv
PRODUCTION=False
MAINTENANCE_MODE=false
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
python data/validate_docs.py
```

Build memerlukan snapshot/arsip sumber yang tersedia di `data/raw/` dan `data/scratch/`. Pengambilan ulang API tidak berjalan otomatis; lihat dokumentasi dataset sebelum memperbarui snapshot.

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
node --test apps/pantry/tests_js/*.test.mjs
node --test apps/budget_planner/tests_js/*.test.mjs
```

Tes PostgreSQL memakai konfigurasi khusus yang **tidak menggunakan kredensial DB PWS**. Jalankan PostgreSQL lokal pada loopback dengan pengguna yang boleh membuat database tes, lalu:

```bash
TEST_PG_PORT=55432 TEST_PG_USER=postgres python manage.py test --settings=config.test_postgres --noinput
```

Jika memakai Docker lokal (bukan terminal PWS), alternatifnya:

```bash
docker run --rm --name takarkuy-test-postgres -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=test-only-password -d postgres:16
TEST_PG_PORT=55432 TEST_PG_USER=postgres TEST_PG_PASSWORD=test-only-password python manage.py test --settings=config.test_postgres --noinput
docker stop takarkuy-test-postgres
```

Password contoh hanya untuk container tes lokal sekali pakai. Jika port sudah dipakai, gunakan port lain dan samakan `TEST_PG_PORT`. Jangan menjalankan dua suite sekaligus dengan nama database PostgreSQL tes yang sama.

Opsional: `TEST_PG_PASSWORD` dan `TEST_PG_DATABASE` (harus berawalan `test_takarkuy_`). Jangan gunakan akun/schema produksi. Tes membuat dan menghapus database tes tersendiri; `db.sqlite3` dan database PWS tidak disentuh. `.github/workflows/tests.yml` menyiapkan PostgreSQL 16 dan menjalankan seluruh tes Python, tes JS dengan glob, serta validator katalog/kandidat/dokumentasi. `TransactionTestCase` di `test_concurrency.py` menguji balapan pembuatan/update/penggantian draft, simpan idempoten, penerapan preview sekali, dan row lock nyata. Tes tersebut sengaja di-skip pada SQLite.

Verifikasi Modul 3 sebelum cleanup fixture pada **5 Oktober 2026** meloloskan suite penuh **347 tes Django di PostgreSQL 16 tanpa skip dan 32 tes JavaScript**. Suite SQLite juga lolos: 330 dijalankan dan 17 tes konkurensi PostgreSQL di-skip. PostgreSQL 16.4 dijalankan secara terisolasi, bukan database PWS. Lint, cek migrasi, build ulang katalog, validator katalog/kandidat/dokumentasi, serta `git diff --check` juga lulus.

Cakupan Modul 3 meliputi index identitas tanpa membedakan kapital, penolakan konflik migrasi tanpa menghapus akun, kompatibilitas login legacy, kuota lintas sesi/worker dan race slot terakhir, CSRF, edit profil berversi, perubahan email dengan password, perubahan password lintas perangkat, maintenance seluruh aplikasi, default preferensi, filter alergi berbasis ID/unknown/bumbu minor, gabungan alergi snapshot/profil, serta pemeriksaan ulang setelah preview/generate. Kontrak dan batas produk dijelaskan di [docs/ACCOUNTS.md](docs/ACCOUNTS.md); mapping mencatat status review dan sumber, bukan klaim keamanan makanan.

Regresi Modul 1 tetap mencakup trial, otorisasi, draft/snapshot, variasi/halal, quote dropdown/preview, budget, riwayat, cleanup/kuota preview, metadata, stale-tab dan idempotensi. Regresi Modul 2 mencakup satu panggilan per scan, cache foto→teks, batch 30 nama, validasi schema, consent koreksi, ledger/migrasi historis, konversi/tanggal, UUID, FEFO, kuota, upload dan deadline transport; detail di [docs/PANTRY.md](docs/PANTRY.md). SQLite IMMEDIATE menserialkan penulis, bukan menyediakan row lock; CI PostgreSQL tetap wajib. Gemini menggunakan mock, bukan verifikasi key/akurasi live; tes JS memakai DOM tiruan, bukan review visual browser. Catatan hasil Modul 3 di atas bersifat historis; Modul 3 dan Modul 4 sudah masuk `main`. Perubahan Modul 5 berada pada branch `modul-5-dashboard`; status CI dan merge mengikuti GitHub. Database PWS/production tidak diubah dan belum diuji. Ruff opsional untuk pengembangan, bukan dependensi runtime.

Cleanup fixture sesudahnya menambahkan satu tes discovery: **3 tes terarah lulus pada PostgreSQL dan 3 pada SQLite**, mencakup fixture tunggal, trial planner katalog aktual, serta input/perpindahan stok pantry. **32 tes JS**, lint, cek migrasi, validator dan build ulang juga lulus. Seluruh 17 keluaran fixture/processed/staging yang diperiksa identik byte per byte; delapan snapshot raw cocok dengan manifest. Suite penuh baru tidak dituntaskan pada mesin lokal yang melambat; CI harus menjalankan seluruh suite setelah push.

## Catatan Deployment PWS

Verifikasi Modul 5 pada **6 Oktober 2026**: **422 tes Django lulus di PostgreSQL tanpa skip dan 48 tes JavaScript lulus**. Ini menggantikan catatan suite lokal yang belum lengkap di atas. Lint, system check, cek migrasi dan validator katalog/kandidat/dokumentasi lulus. Migrasi baru sudah diterapkan lokal tanpa reset data. Layanan peta/Gemini memakai mock dalam tes; browser tidak tersedia sehingga tampilan visual dan provider live belum diverifikasi. Modul 5 belum di-deploy ke PWS; PWS tidak disentuh. Detail ada di [docs/DASHBOARD.md](docs/DASHBOARD.md).

- **Upgrade Modul 3:** jalankan `python manage.py migrate --noinput` untuk model profil/rate limit, metadata alergen dan indeks identitas. Jika preflight melaporkan konflik akun, jangan reset schema/hapus akun: tinjau konflik secara manual. Impor kembali `python manage.py import_catalog data/fixtures/catalog_seed.json` agar mapping alergen masuk database; sebelum impor, semua bahan lama berstatus unknown dan filter alergi menutupnya. Penggantian backend auth dapat membuat sesi lama memerlukan login ulang, tanpa menghapus akun atau stok/rencana. Profil akun lama dibuat otomatis saat digunakan. Pastikan akun staff/superuser tersedia sebelum mengaktifkan maintenance. `AUTH_TRUSTED_PROXY_CIDRS` opsional, berisi CIDR reverse proxy yang benar-benar diverifikasi; jangan memakai `0.0.0.0/0` atau mempercayai X-Forwarded-For tanpa memeriksa proxy.
- **Maintenance seluruh aplikasi:** setelah kode ini di-deploy, set `MAINTENANCE_MODE=true` di environment PWS, lalu restart/redeploy agar proses membaca konfigurasi baru. Landing, daftar/login publik, seluruh modul (termasuk trial guest), dan endpoint API ditutup untuk guest maupun akun biasa dengan HTTP **503**, `Retry-After: 3600` (saran mencoba kembali, bukan janji waktu selesai), dan `Cache-Control: private, no-store`. Request JSON menerima error JSON; halaman menerima tampilan maintenance. View penulisan stok/rencana dan panggilan Gemini tidak dijalankan untuk request yang diblokir. Data dan sesi tidak dihapus. Untuk membuka kembali, set `MAINTENANCE_MODE=false` lalu restart/redeploy; jika variabel tidak ada, default-nya nonaktif. `.env` lokal tidak mengatur PWS.
- **Akses pengelola selama maintenance:** `/admin/login/` tetap tersedia dengan autentikasi dan CSRF bawaan Django Admin; hanya akun aktif berstatus staff yang berhasil login dapat membuka aplikasi untuk pengujian. Login publik `/login/` tetap ditutup. Tidak ada password maintenance, query, header, atau alamat IP untuk bypass. Static files yang benar-benar dilayani WhiteNoise tetap tersedia; tidak ada pengecualian umum untuk semua URL berawalan `/static/`. Middleware ini bukan penghentian container, backup, penguncian database, atau pengganti pembatas upload reverse proxy: admin, background job, dan perintah terminal masih bisa mengubah data, serta request yang sudah berjalan saat restart tidak dibatalkan secara transaksional. Mode ini memerlukan server Django yang bisa berjalan; jika aplikasi gagal start, halaman ini juga tidak dapat disajikan.
- Atur environment PWS terpisah dari `.env` lokal: `PRODUCTION=True`, `DJANGO_SECRET_KEY` yang kuat, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, serta `SCHEMA` sesuai schema yang diberikan. Variabel Gemini opsional sama seperti contoh lokal.
- `PRODUCTION=True` memakai PostgreSQL dan cookie secure; gunakan domain HTTPS yang sudah diizinkan dalam `config/settings.py`. Jangan menggunakan konfigurasi produksi untuk akses HTTP lokal.
- Jalankan `python manage.py migrate --noinput` sebelum impor fixture terbaru, termasuk migrasi `catalog.0002_ingredient_calories_method_text` agar catatan sumber gizi panjang diterima PostgreSQL.
- Alur tanggal otomatis pantry memerlukan migrasi `pantry.0006_pantryitem_ingredient_pantryitem_starting_on_and_more`, yang menambahkan referensi bahan dan tanggal awal. Stok lama tidak dihapus; tanggal ditambahkan digunakan jika tanggal awal belum tercatat.
- Pilihan lokasi pantry hanya **Kulkas, Freezer, dan Suhu Ruang**. Migrasi `pantry.0007_simplify_storage_locations` memindahkan lokasi Lemari Kering lama ke Suhu Ruang tanpa menghapus stok/tanggal yang sudah tersimpan.
- Otorisasi memerlukan migrasi `budget_planner.0001_initial` (kuota guest) dan `pantry.0008_pantryitem_user_pantrynamecorrection_user_and_more` (pemilik stok/koreksi). Data sesi lama dipertahankan dengan `user=NULL`, tidak ditampilkan atau otomatis diklaim oleh akun yang login. Penetapan pemilik data lama harus dilakukan setelah verifikasi, bukan dari ID sesi yang dikirim pengguna.
- Penyimpanan rencana Modul 1 memerlukan migrasi `budget_planner.0002_budgetplan_plannedmeal_planpreview_shoppinglistitem_and_more`. Migrasi menambah tabel rencana, jadwal, daftar belanja, serta pratinjau; tidak menghapus stok/katalog/akun lama. Jalankan migrasi sebelum mengaktifkan kode baru, kemudian `collectstatic` untuk CSS/JavaScript Modul 1.
- Migrasi `budget_planner.0003_preview_draft_identity` menambahkan identitas draft ke preview. Preview lama tanpa identitas dapat ditolak bila ada draft; buat preview baru. Setelah deploy, jalankan `python manage.py import_catalog data/fixtures/catalog_seed.json` untuk memperbarui katalog termasuk menahan instruksi Mendeley. Jangan reset database; guard publikasi menyembunyikan teks Mendeley dari snapshot lama tanpa mengubah data historis.
- Migrasi `budget_planner.0004_preview_quota` menambahkan kuota preview per akun; tidak menghapus data lama. Jalankan `migrate` sebelum memakai kode ini. Jadwalkan `python manage.py cleanup_previews` (misalnya setiap jam melalui scheduler/cron bila tersedia); pembuatan preview juga membersihkan preview akun secara otomatis. Perintah hanya menghapus preview sementara, bukan rencana, menu, stok atau akun.
- Jalankan `python manage.py collectstatic --noinput` dalam alur deployment. Untuk memperbarui katalog, cadangkan database dan gunakan perintah impor fixture lengkap di atas.
- Audit lokal belum memverifikasi PWS, koneksi database produksi, atau Gemini live. Pemeriksaan produksi menemukan peringatan HSTS/pengalihan HTTPS; periksa konfigurasi reverse proxy PWS sebelum mengaktifkannya di Django agar tidak menimbulkan redirect loop.
- Jangan menghapus database/schema sebagai langkah pertama saat deployment gagal. Periksa log aplikasi dan migrasi; reset schema dapat menghapus seluruh akun dan stok pada schema tersebut.

- **Upgrade Modul 4:** jalankan `python manage.py migrate --noinput` (metadata/status panduan dan indeks alergen, gram ledger, favorit/riwayat), lalu `python manage.py import_catalog data/fixtures/catalog_seed.json` dan `python manage.py rebuild_recipe_allergens --check`. Jangan reset database. Jika memakai `loaddata` langsung, lanjutkan dengan `rebuild_recipe_allergens` karena raw fixture tidak memicu signal agregasi. Migrasi tidak menghapus akun/stok/rencana lama. Fitur baru berada di `/modul4/`; beranda tetap `/modul5/`.
- **Upgrade Modul 5:** jalankan `python manage.py migrate --noinput` dan `python manage.py collectstatic --noinput` untuk tabel ulasan/kuota/cache peta dan aset dashboard. Tidak perlu reset atau impor ulang katalog. Pencarian daring default nonaktif; daftar kurasi tetap tersedia tanpa API key. Konfigurasi, sumber dan batas privasi ada di [docs/DASHBOARD.md](docs/DASHBOARD.md). Dua temuan audit rate limit login/proxy PWS tetap perlu diperbaiki sebelum demo; perubahan Modul 5 ini tidak memperbaikinya.

## Otorisasi Saat Ini

Sesudah tiga revisi kecil audit Modul 5 (kuota offline, provider sibuk dan alias HMAC), **44 tes Python terarah lulus di PostgreSQL tanpa skip dan 48 tes JS lulus**. Lint, system check, cek migrasi dan validator dokumentasi lulus. Hasil suite penuh 422 tes di atas berasal dari sebelum revisi ini; suite penuh belum diulang sesudahnya, dan CI PostgreSQL wajib hijau sebelum merge.

Pembatasan berlaku pada backend, bukan hanya tombol navigasi. Halaman Modul 2/3/4/5 mengarahkan guest ke login dengan `next`; API pantry mengembalikan JSON HTTP 401 dan API Recipe Book HTTP 403. CSRF tetap wajib untuk request perubahan data. Pengelolaan resep/bahan di Django Admin terdaftar dengan izin model standar; impor master juga tersedia melalui command.

| Peran | Hak Akses |
| --- | --- |
| Guest | Landing, register/login, dan trial Modul 1: 3 kalkulasi berhasil per 24 jam per browser. Tidak dapat mengakses Modul 2/3/4/5 atau API pantry/Gemini. |
| Registered User | Modul 1 tanpa batas trial guest; stok/profil/rencana/riwayat pribadi; dashboard akun dan modal peta. Ulasan resep terlihat pengguna lain; hanya ulasan sendiri yang boleh diubah/dihapus setelah memasak. |
| Administrator | Django Admin hanya untuk staff dengan izin yang sesuai. Akun staff tidak otomatis mendapat akses stok akun lain melalui API pantry. |

Kuota guest disimpan dalam tabel `GuestTrial`, dengan ID acak bertanda tangan pada cookie HttpOnly. Jendela 24 jam dimulai dari **kalkulasi berhasil pertama**; input tidak valid, error kalkulasi, dan budget belum cukup tidak mengurangi kuota. Pengambilan kuota memakai UPDATE bersyarat atomik sehingga request dengan pembacaan counter lama tidak mendapat slot keempat. Request keempat ditolak HTTP 429 sebelum kalkulasi jika kuota sudah habis. Hasil terakhir disimpan dalam sesi dan tetap dapat dilihat saat reload selama sesi tersebut masih ada. Refresh, logout, atau replay cookie lama tidak mereset kuota; cookie trial memakai Secure di produksi.

**Batas trial:** ini bukan identitas per orang. Menghapus cookie, mode incognito, browser lain, atau menolak cookie bisa melewati batas. Belum ada rate limit IP/global atau pembersihan otomatis baris trial lama. Kuota Gemini sudah per akun/hari (10 foto dan 10 pencocokan nama), tetapi belum merupakan pembatas biaya global atau identitas per orang.

## Deployment dan Desain

- **PWS:** [https://alfredo-nathaniel-takarkuy.pws.cs.ui.ac.id](https://alfredo-nathaniel-takarkuy.pws.cs.ui.ac.id)
- **Figma:** [Desain TAKARKUY](https://www.figma.com/design/GbnAebmRymsFjgLebkKmUJ/PBPUY?node-id=0-1&t=6YqR0aO6YTlJA2SH-1)
