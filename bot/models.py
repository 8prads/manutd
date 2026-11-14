from dataclasses import dataclass

STALE = "__STALE__"  # penanda: berita ternyata basi, jangan dikirim
IRRELEVANT = "__IRRELEVANT__"  # penanda: berita tidak berkaitan dengan Man Utd


@dataclass
class Item:
    uid: str
    title: str
    text: str
    url: str
    source: str            # nama tampilan sumber
    source_id: str
    tier: int              # 1 utama, 2 blog/agregator, 3 API cadangan
    published: float       # epoch UTC
    official: bool = False
    dedicated: bool = True
    journalist: bool = False   # dilaporkan jurnalis tepercaya
    score: int = 0             # skor Reddit
    signal_only: bool = False  # hanya penanda tren, tidak dikirim sendiri
    content: str = ""          # teks penuh bila sumber menyediakan
    undated: bool = False      # sumber tidak mencantumkan tanggal terbit
    max_age_hours: float = 0   # batas umur khusus sumber ini (0 = pakai batas umum)
    mu_only: bool = True       # sumber memang khusus Man Utd (False = hasil pencarian yang bisa nyasar)
