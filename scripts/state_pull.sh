#!/usr/bin/env bash
# Ambil state dari branch `state`. Jika branch belum ada, mulai dari kosong.
# Jika gagal karena masalah jaringan, hentikan run agar state tidak tertimpa.
set -uo pipefail
mkdir -p data
rm -f data/.ok
git ls-remote --exit-code --heads origin state > /dev/null 2>&1
code=$?
if [ "$code" -eq 2 ]; then
  echo "{}" > data/state.json
  echo "branch state belum ada, mulai dari kosong"
elif [ "$code" -eq 0 ]; then
  git fetch --depth=1 origin state || { echo "gagal mengambil state"; exit 1; }
  git show FETCH_HEAD:state.json > data/state.tmp || { echo "state.json tidak terbaca"; exit 1; }
  mv data/state.tmp data/state.json
else
  echo "gagal menghubungi GitHub"; exit 1
fi
touch data/.ok
