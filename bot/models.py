from dataclasses import dataclass

STALE = "__STALE__"  # penanda: berita ternyata basi, jangan dikirim


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
