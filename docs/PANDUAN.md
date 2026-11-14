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

## B. GitHub

1. Buat repo **public** baru, misalnya `manutd-news-bot`.
2. Unggah **isi** folder proyek (bukan file zip) lewat *Add file → Upload files*.
   - Jika folder `.github` tidak ikut terunggah (folder tersembunyi), buat manual: *Add file → Create new file*, ketik nama `.github/workflows/news.yml`, lalu tempel isi dari `docs/news.yml`.
3. **Settings → Secrets and variables → Actions → New repository secret.** Buat dengan nama persis:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`, `GROQ_API_KEY`
   (opsional: `GUARDIAN_API_KEY`, `GNEWS_API_KEY`, `NEWSDATA_API_KEY`).
4. **Settings → Actions → General → Workflow permissions:** pilih **Read and write permissions**, lalu Save. Ini wajib agar bot bisa menyimpan state.
5. Tab **Actions → News Bot → Run workflow**. Dalam satu atau dua menit Telegram menerima pesan `[BOT AKTIF]`. Run pertama hanya mencatat berita yang sudah ada, dan berita baru mulai dikirim di siklus berikutnya.

5. **Data pertandingan (opsional, gratis):** ESPN tidak butuh kunci. Untuk cadangan, buat kunci di <https://dashboard.api-football.com> (API-Football) dan <https://www.football-data.org/client/register> (football-data.org), lalu simpan sebagai secret `API_FOOTBALL_KEY` dan `FOOTBALL_DATA_API_KEY`. Setelah itu kirim `/diagnosa` di Telegram untuk melihat penyedia mana yang berfungsi.

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

`/status` · `/pause` · `/resume` · `/cooldown 15` · `/batas 10` · `/sumber` · `/terakhir` · `/menunggu` · `/pengingat` · `/opini` · `/bantuan`

**Data dan filter:** `/jadwal` (30 hari ke depan, `/jadwal 14` untuk 14 hari), `/klasemen pl|ucl|uel|laliga|seriea|bundesliga|ligue1`, `/statistik` (pertandingan terakhir), `/diagnosa`. Blokir kata: `/blokir bruno contract` (permanen), `/blokir 120 bruno contract` (30-360 menit), `/buka bruno contract`, `/daftarblokir`. Berita [RESMI] tidak pernah diblokir.

**Draf opini:** di Telegram, tekan lama sebuah berita dari bot lalu pilih Reply, ketik `/opini` (boleh ditambah arah opini, misalnya `/opini Carrick perlu diberi waktu`). Atur panjang dengan kata kunci: `singkat` (2-3 kalimat), `3 kalimat`, atau `panjang`; tanpa kata kunci hasilnya 1-2 paragraf pendek, lalu kirim. Dalam satu siklus bot membalas dengan draf opini berpov Anda, mengutip perintah Anda.

**Pengingat token:** bot mengirim pengingat 3 hari sebelum token kedaluwarsa (default 10 November 2027, jam 09:00 WIB). Setelah memperbarui token, atur tanggal baru dengan `/pengingat token_github 2028-11-10`, atau ubah `kedaluwarsa` di `config/settings.yaml`.

Perintah dibaca setiap siklus, jadi balasannya paling lama sekitar 5 menit.

## Jika ada masalah

| Gejala | Cek |
|---|---|
| Tidak ada pesan `[BOT AKTIF]` | Tab Actions, buka run terakhir, baca log. Biasanya secret salah ketik. |
| Run gagal saat "Simpan state" | Workflow permissions belum *Read and write*. |
| Ringkasan berbahasa Inggris | Kunci Gemini/Groq salah, atau kuota gratis habis. Bot akan mencoba lagi. |
| Peringatan "sumber gagal" | Kirim `/sumber` untuk melihat penyebabnya. 403 berarti situs memblokir server GitHub, 404 berarti alamat feed sudah mati. Ganti dengan pencarian Google News per situs (`query: "site:domain.com"`) atau nonaktifkan lewat `config/sources.yaml`. |
| Banyak berita "menunggu" | Kirim `/menunggu` untuk melihat alasannya (cooldown, menunggu dukungan sumber lain, atau batas per jam). Cooldown yang terlalu panjang (`/cooldown`) paling sering menjadi penyebab; 15 menit adalah default. |
| Berita lama ikut terkirim | Kirim `/terakhir` untuk melihat sumber dan tanggal terbit lima berita terakhir, lalu laporkan agar aturannya diperketat. |
| Nama model AI tidak ditemukan | Ubah `llm.gemini_models` atau `llm.groq_models` di `config/settings.yaml`. |


## Memperbarui bot

Timpa file di repo dengan versi baru (state di branch `state` tetap aman dan kompatibel). Secrets dan pengaturan cron-job.org tidak perlu diubah.
