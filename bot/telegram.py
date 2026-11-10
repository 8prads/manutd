"""Klien Telegram sederhana (kirim, edit, ambil perintah)."""
import time


class Telegram:
    def __init__(self, token, chat_id, dry=False, log=print):
        self.token, self.chat_id, self.dry, self.log = token, chat_id, dry, log
        self._n = 0

    def _call(self, method, payload):
        import requests
        for _ in range(3):
            try:
                r = requests.post(f"https://api.telegram.org/bot{self.token}/{method}", json=payload, timeout=20)
            except requests.RequestException as e:
                self.log(f"telegram {method}: {type(e).__name__}")
                time.sleep(2)
                continue
            if r.status_code == 429:
                time.sleep(min(r.json().get("parameters", {}).get("retry_after", 5), 30))
                continue
            if r.ok:
                return r.json().get("result")
            if r.status_code >= 500:
                time.sleep(2)
                continue
            self.log(f"telegram {method}: HTTP {r.status_code} {r.text[:150]}")
            return None
        return None

    def send(self, text):
        if self.dry:
            self._n += 1
            print("----- [DRY] kirim -----\n" + text + "\n-----------------------")
            return self._n
        res = self._call("sendMessage", {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                                         "disable_web_page_preview": True})
        return res["message_id"] if res else None

    def edit(self, message_id, text):
        if self.dry:
            print(f"----- [DRY] edit #{message_id} -----\n{text}\n-----------------------")
            return True
        return self._call("editMessageText", {"chat_id": self.chat_id, "message_id": message_id, "text": text,
                                              "parse_mode": "HTML", "disable_web_page_preview": True}) is not None

    def updates(self, offset):
        if self.dry:
            return []
        return self._call("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": ["message"]}) or []
