# Smart Pantry: kontrak stok dan deployment

## Model dan transaksi

`PantryItem` tetap memakai ID/table lama: satu pembelian = satu batch. Quantity dalam satuan input merupakan saldo utama. `base_unit` mengelompokkan g/ml/pcs; `grams_per_unit` dan `conversion_note` adalah snapshot konversi, bukan saldo terpisah. Volume perlu densitas spesifik; count/pack perlu konversi katalog yang ditinjau atau berat per unit dari pengguna. Berat bagian yang dimakan vs berat bruto harus sesuai bahan katalog; telur 50 g adalah asumsi ukuran large, bukan semua ukuran.

Create/edit/archive menulis `PantryMovement` dan saldo dalam transaksi yang sama. Riwayat menyimpan snapshot sebelum/sesudah, termasuk unit; jangan menjumlahkan selisih angka dari unit berbeda. Semua penulis stok berikutnya wajib melalui layanan/transaksi ini, bukan `QuerySet.update` langsung. API edit mengharuskan `version` integer dan UUID `operation_key`. UUID retry harus tetap; payload berbeda dengan UUID lama ditolak 409. Archiving mengosongkan quantity dan menyimpan ledger. Penghapusan akun memang menghapus stok dan riwayat milik akun tersebut.

Lock selalu berurutan: akun → operasi → batch FEFO (expiry lalu ID). Kuota AI memakai lock akun dan increment bersyarat database. SQLite lokal memakai `transaction_mode=IMMEDIATE` dengan busy timeout 20 detik: transaksi penulis diserialkan sejak BEGIN, bukan dikunci per baris. Ada tes dua koneksi SQLite berbasis file; pengujian ini bukan pengganti tes konkurensi layanan pada PostgreSQL/CI. Beban yang melampaui timeout tetap dapat menghasilkan lock error; gunakan PostgreSQL untuk deployment multi-user.

`consume_stock(user, {ingredient_code: grams}, consumption_key)` hanya layanan internal, belum endpoint memasak. Event unik per akun/UUID, bukan per baris movement; satu event boleh mengonsumsi banyak batch. Stok kurang membatalkan seluruh transaksi. CookingHistory nantinya harus ditulis di transaksi luar yang sama dan memakai key yang sama. Tidak ada reservasi stok oleh hasil rekomendasi. Pengurangan count dibulatkan ke atas pada presisi 0,000001 unit; ledger mengembalikan gram aktual.

## Tanggal dan migrasi

`expiry_source`: label, manual, estimate, legacy, unknown. Label/manual/legacy tidak diubah otomatis. `legacy` berarti tanggal lama dengan asal yang tidak dapat dibuktikan, bukan klaim estimasi/label yang terverifikasi. Estimasi perpindahan berdasarkan tanggal awal, dibatasi tanggal estimasi sebelumnya; `shelf_life_days` mengikuti selisih tanggal aktual (nol diperbolehkan), bukan umur freezer yang belum tentu diterapkan. Tidak ada formula proporsional yang belum tervalidasi dan tidak menghidupkan kembali stok lewat tanggal. Tidak ada acuan → tidak mengarang tanggal. Ini estimasi, bukan penilaian keamanan makanan atau sejarah suhu; [FoodSafety.gov](https://www.foodsafety.gov/keep-food-safe/4-steps-to-food-safety).

Migrasi 0009–0012 mempertahankan ID/pemilik/jumlah/tanggal, menambahkan conversion snapshot dan ledger masuk awal. Migrasi 0012 mengklasifikasikan stok hasil backfill yang belum diedit dan sudah bertanggal sebagai `legacy`; stok tanpa tanggal tetap `unknown`. Tanggal legacy belum lewat dapat kembali dihitung untuk rekomendasi bila bahan/beratnya diketahui; periksa label/kondisinya. Koreksi nama lama dipertahankan tetapi tidak dihitung sebagai konfirmasi manusia sampai dikonfirmasi ulang. Stok tanpa pemilik tidak diberikan ke akun lain. Jangan drop schema/reset database. Sesudah deploy kode dan backup database sesuai kebijakan tim, jalankan:

```sh
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Tanggal unknown/expired, batch archived, bahan belum dipetakan dan berat belum diketahui dikeluarkan dari kecocokan resep. Opsi `allow_unknown_expiry=True` di layanan internal hanya boleh digunakan setelah konfirmasi eksplisit; tetap bukan jaminan keamanan bahan.

Input baru membatasi tanggal belanja sejak 1 Januari 2000 hingga hari ini (Jakarta), dan tanggal kedaluwarsa sejak 2000 hingga maksimal 3.650 hari setelah tanggal belanja. Tanggal historis yang dimigrasikan tidak dihapus/ditulis ulang. API menolak field teks non-string, angka JSON non-finite, dan kedalaman JSON di atas delapan tingkat; decoder recursion error menjadi JSON 400. Riwayat stok yang tidak ditemukan/milik akun lain menjadi JSON 404.

## AI, upload dan batas deployment

Environment Gemini yang sudah ada tidak berubah. Pencocokan nama dan foto masing-masing dibatasi 10 attempt/akun/hari Jakarta, termasuk kegagalan, satu attempt per panggilan bukan per nama. Ini tidak membatasi banyak akun atau total biaya server; tambahkan global budget/rate limit di deployment bila diperlukan. Nama/alias lokal dan cache tetap tersedia saat kuota habis. Cache positif 30 hari, hasil null 1 jam, kegagalan 5 menit; lease 45 detik mencegah request paralel. Kunci v3 memakai nama raw yang dinormalisasi, hash seluruh kode/nama katalog dalam urutan kode tetap, provider dan model efektif. **Tidak memakai daftar kandidat**, sehingga foto dan teks berbagi cache. Saat jalur teks membaca cache, kode wajib masih ada di katalog dan termasuk maksimal lima kandidat lokalnya; jika tidak, lease/cache diperbarui lewat panggilan teks biasa. Versi katalog berubah ketika kode/nama berubah. Cache adalah saran belum dipercaya, tidak mengubah katalog global.

Autofill dari AI maupun cache AI diberi label **dengan AI**. Menekan Simpan saja menyimpan stok, bukan suara koreksi. Checkbox opsional “Nama ini sudah saya periksa” mengirim `accepted=true`; edit nama yang benar-benar berbeda mengirim `user_edited=true`. Hanya koreksi dengan salah satu tindakan tersebut dan padanan katalog yang valid dicatat sebagai `confirmed_by_user`. Koreksi bersama memerlukan minimal 10 akun aktif berumur 7 hari tanpa konflik; ini deklarasi pengguna, bukan bukti bahwa pengguna pasti membaca saran atau verifikasi identitas. Lease milik request dilepas dalam `finally`, termasuk error tak terduga, tanpa menimpa cache yang sudah selesai atau lease milik request lain.

`accepted` dan `user_edited` tetap deklarasi browser yang bisa dipalsukan oleh pemilik akun. Validasi boolean dan padanan kode/nama di server tidak membuktikan interaksi manusia. Ambang usia/jumlah akun mengurangi penyalahgunaan tetapi tidak menggantikan verifikasi identitas atau moderasi.

### Satu panggilan per proses scan

- Tesseract berhasil: koreksi terkonfirmasi → alias/katalog → cache AI tervalidasi → fuzzy. Maksimal 30 nama yang belum dikenal (masing-masing maksimal lima kandidat) dibatch dalam **satu** panggilan teks. Schema `matches[{i,code|null}]`, output budget `40 × jumlah nama + 250`; indeks duplikat/invalid dan kode bukan kandidat ditolak. Angka output budget adalah konfigurasi, bukan hasil pengukuran biaya.
- Tesseract gagal/buram: **satu** panggilan foto membaca sekaligus mencocokkan katalog. Prompt memuat instruksi, katalog berurutan tetap, lalu gambar. Nama pendek yang sama untuk beberapa ID diberi pembeda dari nama asli agar tidak ambigu. Schema `items[{raw,name,quantity,unit,code|null}]`, maksimum 30 baris, output cap 4.000 token. Kode foto divalidasi terhadap katalog saat respons diproses; nama tampil distandardisasi sesuai kode. Raw dipertahankan untuk koreksi/cache. Kode null/invalid hanya dicocokkan lokal.
- Foto gagal/timeout/kosong: pertahankan hasil Tesseract yang tersedia dan lakukan saran lokal dengan `allow_llm=false`; **tidak memanggil Gemini teks**. Respons foto sukses sudah lengkap, sehingga frontend tidak meminta saran AI lagi. Input manual tetap tersedia.

Ini kontrak alur UI per scan, **bukan** pembatas biaya yang tahan client jahat. API client dapat mengirim request baru atau mengubah `allow_llm`; kuota database per akun tetap menjadi pembatas keamanan. Mengunggah ulang foto adalah scan baru. Tidak ada deduplikasi seluruh gambar dan tidak ada image cache. Cache raw→code menghemat pencocokan, bukan menggantikan pembacaan foto buram berikutnya.

Foto tidak diperkecil seragam dan tidak memakai parameter `media_resolution` yang belum diuji pada model terkonfigurasi. Tidak ada klaim penghematan token/resolusi. Transport memakai temperature 0; thinking dinonaktifkan eksplisit hanya untuk model 2.5 Flash/Flash-Lite yang mendukungnya.

### Pengukuran nyata dan privasi

Respons API memuat `ai_usage` untuk panggilan dalam request itu. Transport meneruskan field numerik `usageMetadata`: prompt/output/total/cached/thinking token, jika provider menyediakannya. Log `pantry_ai_call` mencatat task foto/nama, status, durasi, dan angka token saja; tidak mencatat nama, gambar, ID akun, request body, API key, atau response body. Cache/local-only tidak membuat event panggilan. Kegagalan tanpa metadata menghasilkan `tokens={}`, **bukan** klaim nol token/tagihan. Durasi mencakup transport subprocess; jumlah attempt tidak menjamin provider menerima request bila proses gagal dimulai.

Untuk mengukur, buka Network browser, unggah struk uji anonim sekali, dan jumlahkan event `ai_usage` pada respons OCR-fallback/suggestions untuk proses scan itu (maksimal satu). Bandingkan struk jelas, panjang, dan buram; catat juga apakah baris/qty/padanan benar, bukan hanya token. Cross-check log provider dan cache hit sebelum menyatakan penghematan. Tes otomatis memakai mock/sintetik; belum ada benchmark live tanpa foto uji nyata. Format/semantik mengikuti [structured output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) dan [usageMetadata](https://ai.google.dev/api/generate-content#UsageMetadata) resmi. Awalan stabil memberi peluang [implicit cache](https://ai.google.dev/gemini-api/docs/generate-content/caching), bukan jaminan diskon.

Bahasa validasi Django memakai `LANGUAGE_CODE="id"`. Field/JSON yang salah tetap ditolak, bukan diterjemahkan dengan AI.

Backend membatasi foto 10 MB melalui memory upload handler yang dipasang sebelum middleware CSRF. Tidak ada foto maupun teks struk penuh di database/cache. Transport membaca image di memori dan mengirim melalui stdin, bukan file/argv. Proses HTTP Gemini dihentikan dan direap saat deadline total habis (5 detik nama, 25 detik foto); tidak melakukan retry tersembunyi. Response provider dibatasi 256 KiB dan divalidasi. Jangan mengaktifkan logging body request/response provider atau menyimpan receipt dalam trace/APM. Kebijakan penyimpanan Google tetap di luar kontrol aplikasi.

**Batas reverse proxy tetap perlu dikonfigurasi operator PWS**: handler Django tidak mengganti proteksi jaringan/body read timeout pada proxy. Contoh Nginx:

```nginx
location /modul2/ocr-fallback/ {
    client_max_body_size 11m;  # 10 MB file + multipart overhead
    client_body_timeout 30s;
    proxy_pass http://django_upstream;
}
```

Sesuaikan upstream dan aturan lokasi yang sudah ada; jangan menyalin contoh ini tanpa konfigurasi PWS yang sebenarnya. Di PWS yang proxy-nya tidak bisa diedit, minta operator menerapkan cap setara. Perubahan lokal ini **tidak mengubah proxy PWS**. Worker concurrency dan global request rate perlu dibatasi untuk mencegah banyak memory upload/subprocess serentak dari banyak akun.

Script utama Tesseract.js dipin 7.0.0 dengan SHA-384 SRI + crossorigin. SRI itu tidak melindungi worker/core/language assets dinamis; self-host versi yang diverifikasi bila ingin kontrol supply chain penuh. Tes AI memakai mock; tidak menguji key, kuota provider live atau akurasi foto.
