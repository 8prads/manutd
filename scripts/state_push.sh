#!/usr/bin/env bash
# Simpan state ke branch `state` sebagai satu commit tunggal (riwayat tidak menumpuk).
# Hanya berjalan jika state berhasil diambil di awal dan isinya JSON yang valid.
set -euo pipefail
[ -f data/.ok ] && [ -f data/state.json ] || { echo "state tidak diambil, lewati penyimpanan"; exit 0; }
python3 -c "import json;json.load(open('data/state.json'))" || { echo "state tidak valid, lewati"; exit 0; }
tmp="$(mktemp -d)"
cp data/state.json "$tmp/state.json"
cd "$tmp"
git init -q
git checkout -q -b state
git add state.json
git -c user.name="news-bot" -c user.email="news-bot@users.noreply.github.com" commit -q -m "state"
git push -q -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" state
