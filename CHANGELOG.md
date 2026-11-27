# Riwayat Perubahan

Setiap versi mencantumkan file yang berubah, supaya mudah menimpa file yang tepat di repo.

## v1.19 - Pemantauan YouTube, penyedia AI gratis lengkap, kredit Cerebras
- Pemantauan YouTube (`bot/video.py`, YouTube Data API v3, tanpa AI): kanal di `youtube.channels` dipantau tiap 10 menit. Wawancara dan konferensi pers pemain atau petinggi Man Utd dikirim sebagai [VIDEO]; siaran terjadwal sebagai [SIARAN TERJADWAL], lalu [LIVE SEBENTAR LAGI] (30 menit sebelumnya) dan [LIVE], dengan jam WIB dan GMT. Kanal dicari lewat handle lalu nama, dan hasilnya tampil di `/diagnosa`. Pemakaian dibatasi (unit harian dan jatah pencarian); kuota habis atau kunci ditolak menjeda pemantauan dan mengirim peringatan.
- Artikel resmi atau media utama yang mengumumkan jam siaran ("watch live", "how to watch", MUTV) berlabel baru [SIARAN].
- Kutipan wawancara hanya untuk berita yang inti-nya wawancara atau konferensi pers (jenis "wawancara" dari AI, dengan kutipan terverifikasi minimal 80 karakter). Berita yang hanya menyisipkan kutipan memakai format berita biasa; label [INTERVIEW] yang dipicu kata "says" di judul diturunkan menjadi [BERITA], dan wawancara dengan judul lain dinaikkan menjadi [INTERVIEW].
- Penyedia AI baru: GitHub Models (tanpa kunci tambahan), SambaNova, Z.ai, NVIDIA NIM, Cloudflare Workers AI (butuh `CLOUDFLARE_ACCOUNT_ID` juga); Cohere tersedia tetapi dimatikan (kunci uji coba non-komersial). Opsi per penyedia: `enabled`, `needs`, `extra`, `credit_based`, `active_until`, `max_per_day`, `min_interval_seconds`; url boleh memuat `{NAMA_VARIABEL}`.
- Kredit habis: HTTP 402 (atau pesan kredit habis atau kedaluwarsa, atau 403 pada penyedia berbasis kredit) menutup penyedia 30 hari dan mengirim peringatan Telegram; kunci ditolak (401) menutupnya 6 jam; model 404 dilewati 24 jam dan 403 selama 6 jam; semuanya bertahan antar run. Perintah baru `/ai` (status, `/ai tutup <nama> [hari]`, `/ai buka <nama|semua>`).
- `/diagnosa` menampilkan baris YouTube dan menguji semua penyedia AI.
- File: `bot/video.py` (baru), `bot/llm.py`, `bot/draft.py`, `bot/text.py`, `bot/main.py`, `bot/commands.py`, `config/settings.yaml`, `.github/workflows/news.yml`, `docs/news.yml`, `.env.example`, `README.md`, `docs/PANDUAN.md`, `tests/test_v118.py`, `tests/test_v119.py` (baru), `CHANGELOG.md`.

## v1.18 - Headline, kutipan persis, kredibilitas sumber, pemeriksaan AI, multi-penyedia
- Format pesan: tiap bahasa berisi headline satu kalimat (ditulis ulang, berdiri sendiri), lalu isi maksimal 300 karakter (`summary.body_max_chars`, dijaga kode). Berita [RESMI] berawalan "RESMI:" atau "OFFICIAL:". Ringkasan pagi memakai headline.
- Wawancara ([INTERVIEW], [PUNDIT]): konteks lalu kutipan berformat `Nama: “kutipan”. “kutipan”, told @Media.`; kutipan Inggris diperiksa kode persis terhadap artikel (yang tidak ada dibuang), versi Indonesia berisi terjemahan. Akun media ada di `x_handles`.
- Membaca artikel: teks utama diambil dengan `favor_precision`, iklan dan berita terkait dibuang (`cut_boilerplate`), situs berbayar dilewati bila ada sumber lain, dan satu panggilan AI menentukan jenis tulisan, tingkat kepastian, sumber klaim, kutipan, dan penilaian relevan, basi, serta konflik.
- Kredibilitas: golongan A/B (`credibility`) dikirim langsung. Sumber lain (golongan J, termasuk Football365 yang diturunkan dari tier 1) hanya dikirim bila mengutip jurnalis tepercaya dengan kalimat bukti yang ada di teks; nama sumber J tidak ditulis. Satir dibuang, opini dan prediksi berlabel baru [SPEKULASI], klaim yang bertentangan dengan laporan lebih kredibel dibuang. Berita tanpa media A/B tidak dikirim bila AI gagal.
- Pemeriksaan ulang: kode memeriksa angka dan kutipan; untuk transfer, cedera, pelatih, rumor, dan spekulasi, AI dari penyedia berbeda memeriksa makna, kepastian, dan sumber. Draf bermasalah ditulis ulang sekali, dibuang bila masih salah ("gagal periksa"); bila pemeriksa tidak tersedia, berita tetap dikirim dan dicatat.
- AI multi-penyedia: Gemini, Groq, Cerebras, Mistral, OpenRouter (`llm.providers`), urutan terpisah untuk menulis dan memeriksa (`llm.order`). Kuota harian yang habis disimpan di state (`ai_block`) sampai reset, batas per menit dan per hari dihormati, penyedia tanpa kunci dilewati, dan `max_calls_per_run` serta `max_seconds_per_run` membatasi panggilan dan waktu AI per run agar run tidak melewati batas waktu workflow.
- Perintah baru: `/daftar` (nama pemain, staf, jurnalis, pundit), `/jurnalis` (tambah, hapus, reset), `/dibuang` (10 berita terakhir yang dibuang beserta alasan). `/status` menampilkan hitungan per penyedia dan pemeriksaan; `/diagnosa` menguji tiap penyedia. Balasan panjang dipecah otomatis.
- File: `bot/draft.py` (baru), `bot/llm.py`, `bot/pipeline.py`, `bot/commands.py`, `bot/text.py`, `bot/models.py`, `bot/state.py`, `bot/main.py`, `bot/digest.py`, `config/settings.yaml`, `config/sources.yaml`, `.github/workflows/news.yml`, `docs/news.yml`, `.env.example`, `README.md`, `docs/PANDUAN.md`, `tests/test_v118.py` (baru), `tests/test_pipeline.py`, `tests/test_safeguards.py`, `tests/test_v112.py`, `tests/test_v115.py`, `tests/test_v116.py`, `tests/test_v19.py`, `CHANGELOG.md`.

## v1.17 - Pengurai Google News, berita ganda, jadwal ESPN
- Pengurai Google News: pustaka `googlenewsdecoder` 0.2.x mengembalikan kunci `success` (bukan `status`), sehingga semua tautan yang berhasil terurai dianggap gagal. Kini kedua kunci dikenali.
- Anti berita ganda: tautan yang sudah terkirim dalam 48 jam tidak dikirim lagi (`sent_links` di state); state disimpan ke disk setiap selesai kirim sehingga run yang berhenti di tengah tidak mengulang kiriman; `sendMessage` yang kena ReadTimeout tidak dikirim ulang; `state_push.sh` mengulang push sampai 3x.
- ESPN: jadwal tim menjadi sumber utama dan papan skor hanya cadangan (papan skor menjawab HTTP 400 untuk rentang tanggal); `/diagnosa` menampilkan keduanya terpisah.
- File: `bot/football.py`, `bot/llm.py`, `bot/telegram.py`, `bot/pipeline.py`, `bot/main.py`, `bot/state.py`, `scripts/state_push.sh`, `tests/test_v117.py` (baru), `CHANGELOG.md`.

## v1.16 - Perbaikan ESPN (HTTP 400), diagnosa Google News, server AI sibuk
- ESPN: parameter `limit=1000` ternyata ditolak papan skor (HTTP 400); dihapus. Jadwal kini gabungan papan skor dan jadwal tim (saling melengkapi, tanpa duplikat), dan galat hanya muncul bila keduanya gagal.
- `/diagnosa` menambah baris "Google News decode": menguji pengurai pada tautan Google News terbaru di state dan menampilkan hasil mentahnya; log "decode Google News gagal" kini memuat hasil mentah (sebelumnya kosong).
- Gemini/Groq: respons 500/502/503/504 dua kali pada satu model membuat model itu dilewati selama run.
- File: `bot/football.py`, `bot/llm.py`, `bot/commands.py`, `tests/test_v115.py`, `tests/test_v116.py` (baru), `CHANGELOG.md`.

## v1.15 - Jadwal ESPN, waktu Inggris, model AI yang bermasalah
- Jadwal ESPN: permintaan papan skor kini memakai `limit=1000` dan, bila hasilnya kosong, beralih ke jadwal musim milik tim (sebelumnya hanya saat galat, sehingga `/jadwal` jatuh ke football-data.org tanpa Piala dan tanpa id ESPN untuk lineup). `/diagnosa` melaporkan hitungan papan skor dan jadwal tim secara terpisah.
- Jadwal (`/jadwal`, jadwal bulanan) dan pengingat kick-off menampilkan WIB plus waktu Inggris (GMT di musim dingin, BST di musim panas; ubah `UK_ZONE` di `bot/football.py` bila ingin GMT murni).
- Kunci pengingat pertandingan dinormalkan (nama kompetisi dan tim sama untuk semua penyedia) sehingga pengingat tidak terkirim dua kali bila penyedia jadwal berganti; kunci format lama tetap dikenali.
- Model AI: model yang menjawab 404/403, kuota habis, atau timeout dua kali dilewati selama run itu; kuota Gemini habis pada satu model tidak lagi menghentikan model berikutnya. `llama-3.3-70b-versatile` dibuang dari Groq (404), diganti `openai/gpt-oss-20b` sebagai cadangan.
- Highlightly statistik: parser membaca `displayName`, dan pesan galat menampilkan contoh kunci entri statistik.
- `/klasemen`: nama tim tidak lagi terpotong (nama penuh bila muat, jika tidak nama umum seperti Brighton atau Wolves).
- File: `bot/football.py`, `bot/matchday.py`, `bot/llm.py`, `config/settings.yaml`, `docs/PANDUAN.md`, `tests/test_v113.py`, `tests/test_v115.py` (baru), `CHANGELOG.md`.

## v1.14 - Kata kunci nama dan diagnosa lebih jelas
- Perintah `/nama` (`tambah`, `hapus`, `reset`, daftar) untuk menambah atau mengeluarkan nama pemain, staf, dan pelatih tanpa mengedit file; perubahan disimpan di state.
- ESPN: jadwal kini mencoba papan skor lalu jadwal tim, dan galatnya ditampilkan lengkap; parser lebih toleran terhadap bentuk skor dan nama tim.
- Highlightly: pesan galat `/statistik` dan `/diagnosa` menyebut alasan pasti (pertandingan tidak ditemukan, format tidak dikenali) serta pencarian mencoba tanggal sekitar; pencarian id yang gagal diingat 30 menit agar kuota hemat; kuota tampil apa adanya dari respons.
- File: `bot/football.py`, `bot/commands.py`, `bot/text.py`, `bot/pipeline.py`, `bot/main.py`, `README.md`, `docs/PANDUAN.md`, `tests/test_v113.py`, `tests/test_v114.py` (baru), `CHANGELOG.md`.

## v1.13 - Lineup, statistik, dan jadwal lebih rapi
- Highlightly ditambahkan sebagai penyedia lineup dan statistik (kunci gratis `HIGHLIGHTLY_API_KEY`); rantai penyedia: ESPN, Highlightly, API-Football. Id pertandingan disimpan agar kuota 100 per hari hemat.
- `/jadwal` dan jadwal bulanan dirapikan: tiap pertandingan tiga baris (tanggal dan jam WIB, lawan dan kandang/tandang, kompetisi) dengan nama klub dan kompetisi yang dipersingkat.
- Permintaan ESPN memakai User-Agent browser (sebelumnya 403 dari server GitHub); `/diagnosa` menampilkan Highlightly beserta kuota dan contoh kunci respons.
- File: `bot/football.py`, `bot/matchday.py`, `.github/workflows/news.yml`, `docs/news.yml`, `docs/PANDUAN.md`, `tests/test_v112.py`, `tests/test_v113.py` (baru), `CHANGELOG.md`.

## v1.12 - Dua bahasa, data pertandingan, blokir, ringkasan pagi
- Format pesan: label, isi Indonesia, garis, isi Inggris, "Selengkapnya:" dan tautan, lalu sumber (italic). Satu panggilan AI menghasilkan dua bahasa.
- Penjaga berita basi: AI menerima waktu terbit dan daftar judul yang sudah dikirim; umur maksimal 4 jam (Google News 1,5 jam); tanggal situs berbayar tetap dicek.
- Data pertandingan: `/jadwal`, `/klasemen`, `/statistik`, `/diagnosa`; pengingat H-1 dan 1 jam sebelum kick-off, lineup resmi, peringatan jadwal berubah, jadwal bulanan otomatis tiap tanggal 1.
- Ringkasan pagi 07.00 WIB; `/blokir`, `/buka`, `/daftarblokir`; `/status` menampilkan hitungan AI dan pengurai tautan Google News.
- Gemini: waktu berpikir dikurangi dan batas waktu 30 detik.
- File: `bot/football.py` (baru), `bot/matchday.py` (baru), `bot/digest.py` (baru), `bot/llm.py`, `bot/text.py`, `bot/models.py`, `bot/pipeline.py`, `bot/state.py`, `bot/sources.py`, `bot/commands.py`, `bot/main.py`, `config/settings.yaml`, `.github/workflows/news.yml`, `docs/news.yml`, `README.md`, `docs/PANDUAN.md`, `tests/test_v112.py` (baru), `tests/test_integration.py`, `tests/test_safeguards.py`, `CHANGELOG.md`.

## v1.11 - Berita tertahan
- Perintah `/menunggu` menampilkan berita yang tertahan beserta alasannya (cooldown, menunggu dukungan, batas per jam).
- Berita yang tertahan kini dibuang lebih cepat (`expire_minutes` 60, `hold_minutes` 30) agar tidak terkirim saat sudah basi.
- Hitungan gagal lama untuk sumber yang kini hanya dilewati (mis. kuota API habis) dibersihkan, sehingga `/sumber` dan `/status` tidak menampilkan angka usang.
- Label: satu sumber berlabel rumor sudah cukup untuk menandai berita sebagai [RUMOR]; "Papers:" dan "paper talk" dianggap rumor; label [BREAKING NEWS] tidak lagi diberikan hanya karena banyak sumber memberitakan rumor.
- Google News menampilkan The Athletic sebagai "The New York Times"; kini dinamai ulang menjadi The Athletic (`source_aliases`).
- File: `bot/main.py`, `bot/commands.py`, `bot/pipeline.py`, `bot/text.py`, `bot/sources.py`, `config/settings.yaml`, `README.md`, `docs/PANDUAN.md`, `tests/test_v111.py` (baru), `CHANGELOG.md`.

## v1.10 - Batas panggilan API
- Tiap sumber bisa diberi jeda minimum, batas per hari, dan jam aktif (WIB) di `config/sources.yaml`; GNews, NewsData, dan Guardian API sudah diatur agar tidak kena limit walau workflow berjalan tiap 1-2 menit.
- Jika API gratis menjawab kuota habis (402/403/429), sumber itu istirahat sampai pergantian hari UTC dan tidak dihitung sebagai gagal.
- Pencarian Google News diberi jeda 3 menit.
- File: `bot/sources.py`, `config/sources.yaml`, `tests/test_v110.py` (baru), `CHANGELOG.md`.

## v1.9 - Pengurai Google News dan daftar jurnalis
- Tautan Google News diurai menjadi alamat artikel asli (pustaka gratis, opsional) agar isi artikel, nama jurnalis, dan tanggal terbit bisa terbaca; gagal = perilaku lama.
- Daftar jurnalis bertambah 16 nama (James Ducker, Sam Wallace, Jason Burt, Rich Fay, Craig Hope, Alex Crook, Andy Mitten, Miguel Delaney, Ian Irving, Oliver Kay, Daniel Taylor, John Cross, Rob Harris, Graeme Bailey, Simon Peach, Indy Kaila).
- File: `bot/llm.py`, `config/settings.yaml`, `.github/workflows/news.yml`, `docs/news.yml`, `tests/test_v19.py` (baru), `CHANGELOG.md`.

## v1.8 - Panjang opini
- `/opini` kini mengenali kata kunci panjang (`singkat`, `panjang`, `N kalimat`); tanpa kata kunci hasilnya 1-2 paragraf pendek, tidak lagi sangat panjang.
- File: `bot/opini.py`, `bot/commands.py`, `tests/test_v17.py`, `docs/PANDUAN.md`, `CHANGELOG.md`.

## v1.7 - Gaya jurnalis, sumber jurnalis, /opini
- Pesan berita jadi laporan singkat bergaya jurnalis; ringkasan yang berkomentar tentang teks ("tidak ada informasi tambahan") ditolak.
- Sumber menulis nama jurnalis (platform kecil/komunitas diganti nama jurnalis yang dikutip; platform besar tetap).
- Perintah `/opini` (balas sebuah berita) membuat draf opini berpov Anda; semua balasan bot kini mengutip perintah Anda.
- 3 pencarian Google News baru untuk media yang mengutip jurnalis ternama (tabloid, situs olahraga, media umum).
- File: `bot/text.py`, `bot/pipeline.py`, `bot/llm.py`, `bot/opini.py` (baru), `bot/commands.py`, `bot/main.py`, `bot/telegram.py`, `config/settings.yaml`, `config/sources.yaml`, `README.md`, `docs/PANDUAN.md`, `tests/test_commands.py`, `tests/test_v17.py` (baru), `CHANGELOG.md`.

## v1.6 - Daftar nama pemain
- Nama pemain, pelatih, dan staf (`mu_names`) ikut dianggap penanda berita Man Utd, sehingga berita yang judulnya hanya menyebut nama pemain tidak terbuang.
- File: `config/settings.yaml`, `bot/text.py`, `tests/test_safeguards.py`, `CHANGELOG.md`.

## v1.5 - Berita nyasar (basket, dll.)
- Hasil pencarian umum (Google News, GNews, NewsData, Guardian) kini wajib menyebut Man Utd di judul, teks, atau ringkasan; pencarian Google News disaring kata kunci.
- `/terakhir` kini menampilkan kode sumber (mis. `ESPN [gn_main]`) untuk melacak asal berita.
- File: `bot/models.py`, `bot/sources.py`, `bot/pipeline.py`, `bot/commands.py`, `config/sources.yaml`, `tests/test_safeguards.py`, `CHANGELOG.md`.

## v1.4
- Nonaktifkan GDELT (selalu timeout dari server GitHub dan memperlambat siklus).
- File: `config/sources.yaml`, `CHANGELOG.md` (baru).

## v1.3 - Berita tidak relevan
- Pencarian ESPN lewat Google News kini disaring kata kunci Man Utd; AI menandai berita yang tidak berkaitan dengan Man Utd.
- File: `bot/models.py`, `bot/llm.py`, `bot/pipeline.py`, `config/sources.yaml`, `README.md`, `tests/test_safeguards.py`.

## v1.2 - Sumber gagal dan berita basi
- Sumber yang diblokir diganti pencarian Google News per situs; Reddit dinonaktifkan; peringatan digabung dalam satu pesan.
- Penjaga berita basi: verifikasi tanggal halaman, pengecekan AI, sumber baru dicatat diam-diam; perintah `/terakhir`.
- File: `bot/models.py`, `bot/sources.py`, `bot/pipeline.py`, `bot/llm.py`, `bot/main.py`, `bot/commands.py`, `config/settings.yaml`, `config/sources.yaml`, `README.md`, `docs/PANDUAN.md`, `tests/test_safeguards.py` (baru).

## v1.1 - Pengingat
- Pengingat token GitHub dan perintah `/pengingat`.
- File: `bot/reminders.py` (baru), `bot/commands.py`, `bot/main.py`, `bot/state.py`, `config/settings.yaml`, `README.md`, `docs/PANDUAN.md`, `tests/test_reminders.py` (baru).

## v1.0
- Rilis pertama (semua file).
