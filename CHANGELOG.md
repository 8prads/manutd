# Riwayat Perubahan

Setiap versi mencantumkan file yang berubah, supaya mudah menimpa file yang tepat di repo.

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
