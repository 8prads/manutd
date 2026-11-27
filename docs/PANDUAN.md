# Panduan Pemasangan (singkat)

Semua langkah gratis. Total sekitar 20-30 menit.

## A. Siapkan akun dan kunci

1. **Telegram bot:** buka [@BotFather](https://t.me/BotFather), kirim `/newbot`, ikuti langkahnya, lalu simpan **token**-nya.
   - Kirim pesan apa saja ke bot Anda.
   - Buka `https://api.telegram.org/bot<TOKEN>/getUpdates` di browser, cari `"chat":{"id":ANGKA`. Angka itu adalah **chat id**.
2. **Gemini:** buat kunci di <https://aistudio.google.com/apikey>.
3. **Groq:** buat kunci di <https://console.groq.com/keys>.
4. **Guardian (disarankan):** daftar kunci gratis di <https://open-platform.theguardian.com/access>.
5. **GNews dan NewsData (opsional):** <https://gnews.io> dan <https://newsdata.io>.
6. **Penyedia AI tambahan (opsional, satu akun per penyedia).** Makin banyak penyedia, makin kecil peluang kuota habis, karena bot berpindah sendiri. Tanpa kuncinya bot tetap jalan dengan Gemini dan Groq. Jangan membuat beberapa akun di satu penyedia untuk melipatgandakan kuota, karena umumnya melanggar ketentuan layanan. Aturan gratis tiap penyedia sering berubah, jadi cek halaman resminya.
   - **OpenRouter** (<https://openrouter.ai/keys>): secret `OPENROUTER_API_KEY`. Tanpa saldo sekitar 50 permintaan per hari.
   - **SambaNova** (<https://cloud.sambanova.ai>): secret `SAMBANOVA_API_KEY`. Gratis tanpa kartu, sekitar 20 permintaan per hari per model.
   - **Cloudflare Workers AI** (<https://dash.cloudflare.com>): dua secret, `CLOUDFLARE_API_TOKEN` (token API dengan izin Workers AI) dan `CLOUDFLARE_ACCOUNT_ID` (ID akun, ada di dasbor). Gratis sekitar 10 ribu neuron per hari.
   - **Z.ai / Zhipu** (<https://z.ai>): secret `ZAI_API_KEY`. Model Flash gratis, dengan batas bersamaan yang rendah.
   - **NVIDIA NIM** (<https://build.nvidia.com>): secret `NVIDIA_API_KEY`. Butuh verifikasi telepon, kredit awal terbatas, dan syaratnya untuk pengembangan dan uji coba.
   - **Cerebras** (<https://cloud.cerebras.ai>): secret `CEREBRAS_API_KEY`. Butuh kartu untuk mendapat kredit $5, dan kredit kedaluwarsa 30 hari sejak aktivasi. Isi `active_until` di `config/settings.yaml` (tanggal aktivasi + 30 hari) bila ingin bot berhenti memakainya sebelum itu.
   - **GitHub Models**: tanpa kunci tambahan (memakai `GITHUB_TOKEN` workflow dengan izin `models: read`, sudah ada di workflow). Batas masukan sekitar 8 ribu token per permintaan.
   - **Mistral**: secret `MISTRAL_API_KEY` bila akun Anda punya akses gratis. **Cohere** dimatikan di config karena kunci uji cobanya hanya untuk penggunaan non-komersial.
7. **YouTube Data API (untuk pemantauan wawancara dan siaran langsung):** buat project di Google Cloud Console, aktifkan YouTube Data API v3, buat API key, batasi ke API itu, lalu simpan sebagai secret `YOUTUBE_API_KEY`. Kuota gratis bawaan 10.000 unit per hari, dan pemakaian bot jauh di bawahnya.

## B. GitHub

1. Buat repo **public** baru, misalnya `manutd-news-bot`.
2. Unggah **isi** folder proyek (bukan file zip) lewat *Add file → Upload files*.
   - Jika folder `.github` tidak ikut terunggah (folder tersembunyi), buat manual: *Add file → Create new file*, ketik nama `.github/workflows/news.yml`, lalu tempel isi dari `docs/news.yml`.
3. **Settings → Secrets and variables → Actions → New repository secret.** Buat dengan nama persis:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`, `GROQ_API_KEY`
   (opsional: `GUARDIAN_API_KEY`, `GNEWS_API_KEY`, `NEWSDATA_API_KEY`, `YOUTUBE_API_KEY`, dan kunci penyedia AI tambahan: `OPENROUTER_API_KEY`, `SAMBANOVA_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `ZAI_API_KEY`, `NVIDIA_API_KEY`, `CEREBRAS_API_KEY`, `MISTRAL_API_KEY`).
4. **Settings → Actions → General → Workflow permissions:** pilih **Read and write permissions**, lalu Save. Ini wajib agar bot bisa menyimpan state.
5. Tab **Actions → News Bot → Run workflow**. Dalam satu atau dua menit Telegram menerima pesan `[BOT AKTIF]`. Run pertama hanya mencatat berita yang sudah ada, dan berita baru mulai dikirim di siklus berikutnya.

5. **Data pertandingan (opsional, gratis):** jadwal dan klasemen memakai football-data.org (<https://www.football-data.org/client/register>, secret `FOOTBALL_DATA_API_KEY`). Lineup dan statistik memakai Highlightly (<https://highlightly.net>, paket gratis 100 permintaan per hari, secret `HIGHLIGHTLY_API_KEY`). ESPN tidak butuh kunci tetapi sering memblokir server GitHub. API-Football (`API_FOOTBALL_KEY`) paket gratisnya tidak membuka musim berjalan, jadi hanya berguna bila Anda berlangganan. Setelah itu kirim `/diagnosa` di Telegram untuk melihat penyedia mana yang berfungsi.

## C. Pemicu cron-job.org (tiap 5 menit)

1. Di GitHub: **Settings (akun) → Developer settings → Personal access tokens → Fine-grained tokens → Generate.**
   - Repository access: *Only select repositories* → pilih repo ini.
   - Permissions: **Actions = Read and write**.
   - Atur masa berlaku selama mungkin dan catat tanggal kedaluwarsanya. Salin token-nya.
2. Di [cron-job.org](https://cron-job.org) buat cronjob baru:
   - **URL:** `https://api.github.com/repos/USERNAME/NAMA-REPO/actions/workflows/news.yml/dispatches`
   - **Schedule:** setiap 5 menit.
   - **Advanced → Request method:** `POST`.
   - **Headers:**
     `Authorization: Bearer TOKEN_ANDA`
     `Accept: application/vnd.github+json`
     `X-GitHub-Api-Version: 2022-11-28`
   - **Request body:** `{"ref":"main"}`
3. Klik *Test run*. Hasil sukses adalah status **204**.

Jadwal cadangan dari GitHub (tiap 15 menit) sudah ada di workflow dan aman berjalan bersamaan, karena run diantre satu per satu.

## D. Perintah Telegram

`/status` · `/pause` · `/resume` · `/cooldown 15` · `/batas 10` · `/sumber` · `/terakhir` · `/menunggu` · `/dibuang` · `/daftar` · `/jurnalis` · `/ai` · `/pengingat` · `/opini` · `/bantuan`

**Kata kunci nama:** `/nama` menampilkan daftar pemain dan staf yang dikenali bot. `/nama tambah Hojlund` menambah nama (mis. pembelian baru), `/nama hapus Rashford` mengeluarkan nama yang sudah pergi, `/nama reset` membatalkan semua perubahan lewat Telegram. Perubahan tersimpan dan berlaku mulai siklus berikutnya; daftar bawaan ada di `mu_names` pada `config/settings.yaml`.

**Daftar nama:** `/daftar` menampilkan seluruh nama pemain dan staf, jurnalis tepercaya, dan pundit yang dikenali bot. `/jurnalis` bekerja seperti `/nama` untuk daftar jurnalis: `/jurnalis tambah Nama Lengkap`, `/jurnalis hapus Nama`, `/jurnalis reset`. Daftar jurnalis penting karena menentukan sumber non-utama mana yang boleh dikirim. Perbarui tiap musim, lalu kirim `/jurnalis reset` bila ingin kembali ke daftar di `config/settings.yaml`.

**Berita yang dibuang:** `/dibuang` menampilkan 10 berita terakhir yang dibuang beserta alasannya (tidak kredibel, satir, bertentangan, gagal periksa, basi, duplikat, dan seterusnya). Bila ada berita bagus yang terbuang karena jurnalisnya belum masuk daftar, tambahkan dengan `/jurnalis tambah`.

**Format pesan:** tiap bahasa berisi headline satu kalimat yang memancing rasa penasaran (formal, bukan kalimat tanya, tanpa kata dramatis), lalu isi yang merangkum seluruh berita dalam maksimal 5 kalimat (`summary.max_sentences`) dan 1024 karakter (`summary.body_max_chars`). Pemisah bahasa (garis) selalu ada di antara versi Indonesia dan Inggris. Cocok untuk memposting headline lebih dulu, lalu isi terjadwal sebagai kutipan headline-nya. Berita `[RESMI]` berawalan "RESMI:" atau "OFFICIAL:". Untuk berita yang inti-nya wawancara atau konferensi pers (ditentukan AI; berita yang sekadar menyisipkan kutipan tetap berformat berita biasa), isinya konteks lalu kutipan: `Nama: “kutipan”. “kutipan”, told @Media.` Kutipan Inggris diperiksa persis terhadap artikel, dan kutipan yang tidak ditemukan dibuang. Akun X media ada di `x_handles` pada `config/settings.yaml`; periksa dan sesuaikan.

**Kredibilitas sumber:** media golongan A dan B (`credibility` di `config/settings.yaml`) dikirim langsung. Sumber lain hanya dikirim bila artikelnya mengutip jurnalis tepercaya dengan kalimat bukti yang ada di teks; nama sumber itu tidak ditulis, yang ditulis nama jurnalisnya. Opini dan prediksi diberi label `[SPEKULASI]`, satir dibuang.

**Pemeriksaan AI dan penyedia:** untuk berita transfer, cedera, pelatih, rumor, dan spekulasi, AI kedua dari penyedia yang berbeda memeriksa draf terhadap artikel (`llm.check_types` dan `llm.check_labels`). Urutan penyedia untuk menulis dan memeriksa diatur di `llm.order`. Kuota harian yang habis diingat sampai reset; penyedia berbasis kredit (Cerebras, NVIDIA) ditutup 30 hari begitu kredit habis atau kedaluwarsa, dan bot mengirim peringatan. `/ai` menampilkan status tiap penyedia; `/ai tutup cerebras 30` menutup penyedia secara manual, dan `/ai buka cerebras` atau `/ai buka semua` membukanya lagi. `/status` menampilkan hitungan per penyedia dan hasil pemeriksaan, dan `/diagnosa` menguji tiap penyedia yang kuncinya ada dengan satu panggilan kecil.

**Pemantauan YouTube:** butuh `YOUTUBE_API_KEY`. Kanal ada di `youtube.channels` pada `config/settings.yaml` (tambah atau hapus dengan mengedit daftar). Bot mencari tiap kanal lewat handle, lalu lewat nama bila handle salah; `/diagnosa` menampilkan kanal yang terpilih beserta jumlah pelanggannya, jadi pastikan bukan kanal tiruan. Video yang judulnya memuat kata wawancara atau konferensi pers dan menyebut Man Utd atau nama pemain/stafnya dikirim sebagai `[VIDEO]`; kanal resmi klub cukup memuat kata wawancara. Siaran terjadwal dikirim sebagai `[SIARAN TERJADWAL]`, lalu `[LIVE SEBENTAR LAGI]` (30 menit sebelum mulai) dan `[LIVE]`. Berjalan setiap 10 menit, memakai kurang dari 2.000 unit per hari, dan tidak memakai kuota AI. Artikel ManUtd.com yang mengumumkan jam siaran muncul sebagai `[SIARAN]`.

**Data dan filter:** `/jadwal` (30 hari ke depan, `/jadwal 14` untuk 14 hari; jam ditampilkan dalam WIB dan waktu Inggris GMT/BST), `/klasemen pl|ucl|uel|laliga|seriea|bundesliga|ligue1`, `/statistik` (pertandingan terakhir), `/diagnosa`. Blokir kata: `/blokir bruno contract` (permanen), `/blokir 120 bruno contract` (30-360 menit), `/buka bruno contract`, `/daftarblokir`. Berita [RESMI] tidak pernah diblokir.

**Draf opini:** di Telegram, tekan lama sebuah berita dari bot lalu pilih Reply, ketik `/opini` (boleh ditambah arah opini, misalnya `/opini Carrick perlu diberi waktu`). Atur panjang dengan kata kunci: `singkat` (2-3 kalimat), `3 kalimat`, atau `panjang`; tanpa kata kunci hasilnya 1-2 paragraf pendek, lalu kirim. Dalam satu siklus bot membalas dengan draf opini berpov Anda, mengutip perintah Anda.

**Pengingat token:** bot mengirim pengingat 3 hari sebelum token kedaluwarsa (default 10 November 2027, jam 09:00 WIB). Setelah memperbarui token, atur tanggal baru dengan `/pengingat token_github 2028-11-10`, atau ubah `kedaluwarsa` di `config/settings.yaml`.

Perintah dibaca setiap siklus, jadi balasannya paling lama sekitar 5 menit.

## Jika ada masalah

| Gejala | Cek |
|---|---|
| Tidak ada pesan `[BOT AKTIF]` | Tab Actions, buka run terakhir, baca log. Biasanya secret salah ketik. |
| Run gagal saat "Simpan state" | Workflow permissions belum *Read and write*. |
| Ringkasan berbahasa Inggris atau berita tertahan | Kunci AI salah, atau kuota gratis habis. Kirim `/status` dan `/diagnosa` untuk melihat penyedia mana yang gagal. Berita yang tidak punya media golongan A/B tidak dikirim tanpa AI. |
| Berita bagus tidak muncul | Kirim `/dibuang` untuk melihat alasannya. Bila jurnalisnya belum ada di daftar, tambahkan dengan `/jurnalis tambah`. |
| Tidak ada pesan `[VIDEO]` atau `[LIVE]` | Kirim `/diagnosa` dan lihat baris YouTube: kunci belum dipasang, kanal belum ditemukan, atau kuota API habis. Pesan peringatan juga dikirim bila API menolak kunci. |
| Penyedia AI berhenti dipakai | Kirim `/ai`. Penyedia berbasis kredit ditutup 30 hari setelah kredit habis; buka lagi dengan `/ai buka <nama>` bila kreditnya sudah diisi. |
| Kuota AI cepat habis | Tambahkan penyedia gratis lain (Cerebras, Mistral, OpenRouter) lewat GitHub Secrets. Pantau hitungan di `/status`. |
| Peringatan "sumber gagal" | Kirim `/sumber` untuk melihat penyebabnya. 403 berarti situs memblokir server GitHub, 404 berarti alamat feed sudah mati. Ganti dengan pencarian Google News per situs (`query: "site:domain.com"`) atau nonaktifkan lewat `config/sources.yaml`. |
| Banyak berita "menunggu" | Kirim `/menunggu` untuk melihat alasannya (cooldown, menunggu dukungan sumber lain, atau batas per jam). Cooldown yang terlalu panjang (`/cooldown`) paling sering menjadi penyebab; 15 menit adalah default. |
| Berita lama ikut terkirim | Kirim `/terakhir` untuk melihat sumber dan tanggal terbit lima berita terakhir, lalu laporkan agar aturannya diperketat. |
| Nama model AI tidak ditemukan (404 di log atau `/diagnosa`) | Ubah `models` pada penyedia terkait di `llm.providers` pada `config/settings.yaml`. |


## Memperbarui bot

Timpa file di repo dengan versi baru (state di branch `state` tetap aman dan kompatibel). Secrets dan pengaturan cron-job.org tidak perlu diubah.
