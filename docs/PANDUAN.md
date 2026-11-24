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
6. **Penyedia AI tambahan (opsional, gratis, satu akun per penyedia):** Cerebras (<https://cloud.cerebras.ai>), Mistral (<https://console.mistral.ai>), dan OpenRouter (<https://openrouter.ai/keys>). Makin banyak penyedia, makin kecil peluang kuota habis, karena bot berpindah sendiri. Tanpa kuncinya bot tetap jalan dengan Gemini dan Groq. Jangan membuat beberapa akun di satu penyedia untuk melipatgandakan kuota, karena umumnya melanggar ketentuan layanan.

## B. GitHub

1. Buat repo **public** baru, misalnya `manutd-news-bot`.
2. Unggah **isi** folder proyek (bukan file zip) lewat *Add file → Upload files*.
   - Jika folder `.github` tidak ikut terunggah (folder tersembunyi), buat manual: *Add file → Create new file*, ketik nama `.github/workflows/news.yml`, lalu tempel isi dari `docs/news.yml`.
3. **Settings → Secrets and variables → Actions → New repository secret.** Buat dengan nama persis:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`, `GROQ_API_KEY`
   (opsional: `GUARDIAN_API_KEY`, `GNEWS_API_KEY`, `NEWSDATA_API_KEY`, `CEREBRAS_API_KEY`, `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`).
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

`/status` · `/pause` · `/resume` · `/cooldown 15` · `/batas 10` · `/sumber` · `/terakhir` · `/menunggu` · `/dibuang` · `/daftar` · `/jurnalis` · `/pengingat` · `/opini` · `/bantuan`

**Kata kunci nama:** `/nama` menampilkan daftar pemain dan staf yang dikenali bot. `/nama tambah Hojlund` menambah nama (mis. pembelian baru), `/nama hapus Rashford` mengeluarkan nama yang sudah pergi, `/nama reset` membatalkan semua perubahan lewat Telegram. Perubahan tersimpan dan berlaku mulai siklus berikutnya; daftar bawaan ada di `mu_names` pada `config/settings.yaml`.

**Daftar nama:** `/daftar` menampilkan seluruh nama pemain dan staf, jurnalis tepercaya, dan pundit yang dikenali bot. `/jurnalis` bekerja seperti `/nama` untuk daftar jurnalis: `/jurnalis tambah Nama Lengkap`, `/jurnalis hapus Nama`, `/jurnalis reset`. Daftar jurnalis penting karena menentukan sumber non-utama mana yang boleh dikirim. Perbarui tiap musim, lalu kirim `/jurnalis reset` bila ingin kembali ke daftar di `config/settings.yaml`.

**Berita yang dibuang:** `/dibuang` menampilkan 10 berita terakhir yang dibuang beserta alasannya (tidak kredibel, satir, bertentangan, gagal periksa, basi, duplikat, dan seterusnya). Bila ada berita bagus yang terbuang karena jurnalisnya belum masuk daftar, tambahkan dengan `/jurnalis tambah`.

**Format pesan:** tiap bahasa berisi headline satu kalimat, lalu isi maksimal 300 karakter (`summary.body_max_chars`). Berita `[RESMI]` berawalan "RESMI:" atau "OFFICIAL:". Untuk `[INTERVIEW]` dan `[PUNDIT]`, isinya konteks lalu kutipan: `Nama: “kutipan”. “kutipan”, told @Media.` Kutipan Inggris diperiksa persis terhadap artikel, dan kutipan yang tidak ditemukan dibuang. Akun X media ada di `x_handles` pada `config/settings.yaml`; periksa dan sesuaikan.

**Kredibilitas sumber:** media golongan A dan B (`credibility` di `config/settings.yaml`) dikirim langsung. Sumber lain hanya dikirim bila artikelnya mengutip jurnalis tepercaya dengan kalimat bukti yang ada di teks; nama sumber itu tidak ditulis, yang ditulis nama jurnalisnya. Opini dan prediksi diberi label `[SPEKULASI]`, satir dibuang.

**Pemeriksaan AI dan penyedia:** untuk berita transfer, cedera, pelatih, rumor, dan spekulasi, AI kedua dari penyedia yang berbeda memeriksa draf terhadap artikel (`llm.check_types` dan `llm.check_labels`). Urutan penyedia untuk menulis dan memeriksa diatur di `llm.order`. `/status` menampilkan hitungan per penyedia dan hasil pemeriksaan. `/diagnosa` menguji tiap penyedia yang kuncinya ada dengan satu panggilan kecil.

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
| Kuota AI cepat habis | Tambahkan penyedia gratis lain (Cerebras, Mistral, OpenRouter) lewat GitHub Secrets. Pantau hitungan di `/status`. |
| Peringatan "sumber gagal" | Kirim `/sumber` untuk melihat penyebabnya. 403 berarti situs memblokir server GitHub, 404 berarti alamat feed sudah mati. Ganti dengan pencarian Google News per situs (`query: "site:domain.com"`) atau nonaktifkan lewat `config/sources.yaml`. |
| Banyak berita "menunggu" | Kirim `/menunggu` untuk melihat alasannya (cooldown, menunggu dukungan sumber lain, atau batas per jam). Cooldown yang terlalu panjang (`/cooldown`) paling sering menjadi penyebab; 15 menit adalah default. |
| Berita lama ikut terkirim | Kirim `/terakhir` untuk melihat sumber dan tanggal terbit lima berita terakhir, lalu laporkan agar aturannya diperketat. |
| Nama model AI tidak ditemukan (404 di log atau `/diagnosa`) | Ubah `models` pada penyedia terkait di `llm.providers` pada `config/settings.yaml`. |


## Memperbarui bot

Timpa file di repo dengan versi baru (state di branch `state` tetap aman dan kompatibel). Secrets dan pengaturan cron-job.org tidak perlu diubah.
