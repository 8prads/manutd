"""Inti bot: gabungkan berita sama, terapkan cooldown, batas, lalu kirim."""
import time

from . import text as T
from .models import IRRELEVANT, STALE


class Pipeline:
    def __init__(self, cfg, state, tg, summarize, now=time.time, log=print):
        self.cfg, self.st, self.tg, self.summarize = cfg, state, tg, summarize
        self.now, self.log = now, log
        self.rel = T.build_relevance(cfg)
        self.pundit_re = T.build_pundit_re(cfg)
        names = cfg["people"]["trusted_journalists"] + cfg["people"]["pundits"] + cfg.get("entities_seed", [])
        self.seed = {t for n in names for t in T.tokens(n)}
        self.jr = T.build_journalist_re(cfg)
        self.big = {x.lower() for x in cfg.get("big_platforms", []) + cfg["tier1_names"]}

    # ---------- pengaturan (bisa diubah lewat Telegram) ----------
    @property
    def cooldown_s(self):
        return 60 * self.st["override"].get("cooldown_minutes", self.cfg["cooldown"]["minutes"])

    @property
    def max_per_hour(self):
        return self.st["override"].get("max_per_hour", self.cfg["rate"]["max_per_hour"])

    # ---------- belajar kosakata (untuk bobot IDF) ----------
    def _learn(self, toks, it=None):
        if it is not None:
            T.learn_caps(self.st["caps"], it.title, it.text)
        df = self.st["df"]
        for t in toks:
            df[t] = df.get(t, 0) + 1
        self.st["n_docs"] += 1
        if self.st["n_docs"] > 6000:
            self.st["df"] = {k: v // 2 for k, v in df.items() if v // 2 > 0}
            self.st["n_docs"] //= 2

    def bootstrap(self, items):
        """Run pertama: tandai semua berita yang ada sebagai sudah dilihat tanpa mengirim."""
        now = self.now()
        for it in items:
            self.st["seen"][it.uid] = now
            self._learn(T.tokens(f"{it.title} {it.text[:300]}"), it)

    # ---------- masuk ----------
    def ingest(self, items):
        now, d = self.now(), self.cfg["dedupe"]
        max_age = self.cfg["max_item_age_hours"] * 3600
        seen = self.st["seen"]
        for it in sorted(items, key=lambda x: x.published):
            if it.uid in seen:
                continue
            seen[it.uid] = now
            toks = T.tokens(f"{it.title} {it.text[:300]}")
            self._learn(toks, it)
            if not T.is_relevant(it, self.rel) or now - it.published > max_age:
                continue
            et = T.event_type(f"{it.title} {it.text[:300]}")
            lab = self._item_label(it, et)
            jn = T.find_journalists(f"{it.title} {it.text} {it.content[:4000]}", self.jr)
            if it.journalist and it.source not in jn:
                jn.insert(0, it.source)
            story = self._match(toks, et, it, d)
            if story and story["status"] == "sent" and T.rank(lab) > T.rank(story["label"]):
                story = None  # naik tingkat (mis. RUMOR -> RESMI): jadikan berita baru
            if story:
                self._attach(story, it, d, lab, jn)
            elif not it.signal_only:
                self._new_story(it, toks, et, lab, jn)

    def _match(self, toks, et, it, d):
        df, n = self.st["df"], self.st["n_docs"]
        ents = set(self._entities(toks))
        ttoks = T.tokens(it.title)
        best, best_sim = None, 0.0
        for s in self.st["stories"].values():
            if s["status"] not in ("pending", "sent"):
                continue
            sim = max(T.wjaccard(toks, s["tokens"], df, n), T.wjaccard(ttoks, s.get("ttokens", []), df, n))
            weak = (
                d["weak_threshold"] <= sim < d["strong_threshold"] and et == s["etype"] and et in T.STRONG_TYPES
                and ents & set(s["ents"]) and abs(it.published - s["pub"]) <= 7200
            )
            mid = sim >= d["mid_threshold"] and len(ents & set(s["ents"])) >= 2
            if (sim >= d["strong_threshold"] or mid or weak) and sim > best_sim:
                best, best_sim = s, sim
        return best

    def _entities(self, toks):
        return T.entities(toks, self.st["caps"], self.seed, self.st["df"], self.st["n_docs"])

    def _item_label(self, it, et):
        strong = it.tier == 1 or it.journalist
        return T.classify(it.title, it.text, it.official, strong, 1, et, self.pundit_re)

    def _new_story(self, it, toks, et, lab, jn):
        df, n = self.st["df"], self.st["n_docs"]
        self.st["stories"][it.uid] = {
            "id": it.uid, "title": it.title, "text": it.text[:600], "tokens": toks[:40], "ttokens": T.tokens(it.title)[:20],
            "ents": self._entities(toks), "etype": et,
            "facts": sorted(T.facts(f"{it.title} {it.text[:400]}")), "pub": it.published,
            "first_seen": self.now(), "status": "pending", "retries": 0,
            "sources": [{"name": it.source, "tier": it.tier, "url": it.url, "label": lab, "sid": it.source_id}],
            "official": it.official, "journalist": it.journalist, "reddit": it.score, "verify": it.undated,
            "mu_only": it.mu_only, "journalists": list(jn),
            "signals": [], "content": it.content[: self.cfg["summary"]["max_article_chars"]],
            "msg_id": None, "body": None, "label": None, "sent_at": None,
            "needs_edit": False, "edits": 0,
        }

    def _attach(self, s, it, d, lab, jn):
        if it.signal_only:
            if it.source not in s["signals"]:
                s["signals"].append(it.source)
            return
        for j in jn:
            if j not in s.setdefault("journalists", []):
                s["journalists"].append(j)
        if it.source not in {x["name"] for x in s["sources"]}:
            s["sources"].append({"name": it.source, "tier": it.tier, "url": it.url, "label": lab, "sid": it.source_id})
            if (s["status"] == "sent" and self.now() - s["sent_at"] <= d["merge_window_minutes"] * 60
                    and s["edits"] < d["max_edits"]):
                s["needs_edit"] = True
        s["official"] = s["official"] or it.official
        s["verify"] = s.get("verify", False) and it.undated
        s["mu_only"] = s.get("mu_only", False) or it.mu_only
        s["journalist"] = s["journalist"] or it.journalist
        s["reddit"] = max(s["reddit"], it.score)
        if it.content and not s["content"]:
            s["content"] = it.content[: self.cfg["summary"]["max_article_chars"]]

    # ---------- keputusan kirim ----------
    @staticmethod
    def _best_tier(s):
        return min(x["tier"] for x in s["sources"])

    def source_names(self, s):
        """Platform besar ditulis apa adanya. Platform kecil/komunitas diganti nama jurnalis bila ada."""
        journ = list(s.get("journalists", []))
        order = sorted(enumerate(s["sources"]), key=lambda p: (p[1]["tier"], p[0]))
        bigs, smalls = [], []
        for _, x in order:
            n = x["name"]
            if n in journ:
                continue
            (bigs if n.lower() in self.big else smalls).append(n)
        names = bigs + journ + ([] if journ else smalls)
        out = []
        for n in names:
            if n not in out:
                out.append(n)
        return out or [s["sources"][0]["name"]]

    def _eligible(self, s):
        if s["official"] or s["journalist"] or self._best_tier(s) == 1:
            return True
        tr = self.cfg["trend"]
        if not tr["small_sources_need_support"]:
            return True
        if len({x["name"] for x in s["sources"]}) >= 2 or s["reddit"] >= tr["reddit_min_score"]:
            return True
        return len(s["signals"]) >= tr["gdelt_min_domains"]

    def _label(self, s):
        labels = [x["label"] for x in s["sources"]]
        top = max(labels, key=T.rank)
        if T.rank(top) >= 3:
            return top  # RESMI atau BREAKING dari salah satu sumber
        if "RUMOR" in labels:
            return "RUMOR"  # satu sumber saja yang berhati-hati sudah cukup untuk menandai rumor
        strong = s["journalist"] or self._best_tier(s) == 1
        if strong and s["etype"] in T.FACT_TYPES and len({x["name"] for x in s["sources"]}) >= 3:
            return "BREAKING NEWS"
        return top

    def _priority(self, s):
        unlimited = self._label(s) in self.cfg["rate"]["unlimited_labels"]
        return (0 if unlimited else 1, self._best_tier(s), -len(s["sources"]), s["first_seen"])

    def _find_topic(self, s):
        now = self.now()
        for t in self.st["topics"]:
            if now - t["last_sent"] <= 10800 and t["type"] == s["etype"] and set(t["tokens"]) & set(s["ents"]):
                return t
        return None

    def _bypass(self, s, label, topic):
        c = self.cfg["cooldown"]
        if c["bypass_on_escalation"] and T.rank(label) > topic["rank"]:
            return True
        if c["bypass_on_new_facts"] and s["etype"] in T.FACT_TYPES and set(s["facts"]) - set(topic["facts"]):
            return True
        return False

    def _record_topic(self, s, label):
        t = self._find_topic(s)
        now = self.now()
        if t:
            t.update(last_sent=now, rank=max(t["rank"], T.rank(label)),
                     facts=sorted(set(t["facts"]) | set(s["facts"])))
        else:
            self.st["topics"].append({"type": s["etype"], "tokens": s["ents"], "last_sent": now,
                                      "rank": T.rank(label), "facts": s["facts"]})

    def _sent_last_hour(self):
        cut = self.now() - 3600
        return sum(1 for t in self.st["sent_log"] if t >= cut)

    def _mentions_mu(self, s, extra=""):
        keys = self.rel[0]
        return bool(keys and keys.search(f"{s['title']} {s['text']} {s.get('content', '')} {extra}"))

    def _fallback_body(self, s):
        sentences = [x.strip() for x in (s["text"] or s["title"]).replace("\n", " ").split(". ") if x.strip()]
        body = ". ".join(sentences[:3]) or s["title"]
        if not body.endswith("."):
            body += "."
        return "(Ringkasan dalam bahasa Inggris karena layanan terjemahan sedang bermasalah.) " + body

    def pending_report(self):
        """Daftar berita yang menunggu beserta alasannya: (judul, umur_menit, alasan, label)."""
        now, tr = self.now(), self.cfg["trend"]
        out = []
        pend = sorted((s for s in self.st["stories"].values() if s["status"] == "pending"), key=lambda s: s["first_seen"])
        for s in pend:
            age = (now - s["first_seen"]) / 60
            label = self._label(s)
            topic = self._find_topic(s)
            if not self._eligible(s):
                reason = f"menunggu dukungan sumber lain ({max(0, int(tr['hold_minutes'] - age))} mnt lagi sebelum dibuang)"
            elif topic and now - topic["last_sent"] < self.cooldown_s and not self._bypass(s, label, topic):
                reason = f"cooldown topik ({int((self.cooldown_s - (now - topic['last_sent'])) / 60) + 1} mnt lagi)"
            elif label not in self.cfg["rate"]["unlimited_labels"] and self._sent_last_hour() >= self.max_per_hour:
                reason = "batas pesan per jam tercapai"
            else:
                reason = "antre untuk siklus berikutnya"
            out.append((s["title"], int(age), reason, label))
        return out

    def dispatch(self):
        now = self.now()
        tr, unlimited = self.cfg["trend"], self.cfg["rate"]["unlimited_labels"]
        pend = [s for s in self.st["stories"].values() if s["status"] == "pending"]
        pend.sort(key=self._priority)
        sent = 0
        for s in pend:
            age = now - s["first_seen"]
            if age > tr["expire_minutes"] * 60:
                s["status"], s["drop"] = "dropped", "kedaluwarsa"
                continue
            if not self._eligible(s):
                if age > tr["hold_minutes"] * 60:
                    s["status"], s["drop"] = "dropped", "tidak naik"
                continue
            label = self._label(s)
            topic = self._find_topic(s)
            if topic and now - topic["last_sent"] < self.cooldown_s and not self._bypass(s, label, topic):
                continue
            if label not in unlimited and self._sent_last_hour() >= self.max_per_hour:
                continue
            body = self.summarize(s)
            if body in (STALE, IRRELEVANT):
                s["status"], s["drop"] = "dropped", "basi" if body == STALE else "tidak relevan"
                self.log(f"dibuang ({s['drop']}): {s['title'][:70]}")
                continue
            if (not body and not self._mentions_mu(s)) or (
                    not s.get("mu_only", True) and not self._mentions_mu(s, body or "")):
                # Hasil pencarian umum wajib menyebut Man Utd di judul, teks, atau ringkasan
                s["status"], s["drop"] = "dropped", "tidak relevan"
                self.log(f"dibuang (tidak menyebut Man Utd): {s['title'][:70]}")
                continue
            if not body:
                s["retries"] += 1
                if s["retries"] <= self.cfg["summary"]["retry_cycles"]:
                    continue
                body = self._fallback_body(s)
            mid = self.tg.send(T.format_message(label, body, self.source_names(s)))
            if mid is None:
                continue
            s.update(status="sent", msg_id=mid, body=body, label=label, sent_at=now, needs_edit=False)
            self._record_topic(s, label)
            if label not in unlimited:
                self.st["sent_log"].append(now)
            sent += 1
            self.log(f"terkirim [{label}] {s['title'][:70]} | terbit {time.strftime('%Y-%m-%d %H:%M', time.gmtime(s['pub']))} UTC")
        return sent

    def refresh_edits(self):
        for s in self.st["stories"].values():
            if s["status"] == "sent" and s["needs_edit"]:
                self.tg.edit(s["msg_id"], T.format_message(s["label"], s["body"], self.source_names(s)))
                s["needs_edit"] = False
                s["edits"] += 1

    # ---------- bersih-bersih ----------
    def prune(self):
        now = self.now()
        keep = self.cfg["dedupe"]["retention_hours"] * 3600
        st = self.st
        st["seen"] = {k: v for k, v in st["seen"].items() if now - v < keep + 86400}
        st["stories"] = {k: s for k, s in st["stories"].items()
                         if now - s["first_seen"] < keep or s["status"] == "pending"}
        st["topics"] = [t for t in st["topics"] if now - t["last_sent"] < 10800]
        st["sent_log"] = [t for t in st["sent_log"] if now - t < 7200]
