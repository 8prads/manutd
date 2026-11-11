# Riwayat Perubahan

Setiap versi mencantumkan file yang berubah, supaya mudah menimpa file yang tepat di repo.

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
