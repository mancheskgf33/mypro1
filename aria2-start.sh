#!/bin/sh
set -eu
aria2c \
  --enable-rpc=true \
  --rpc-listen-all=false \
  --rpc-listen-port=6800 \
  --continue=true \
  --allow-overwrite=true \
  --auto-file-renaming=true \
  --max-concurrent-downloads=5 \
  --max-connection-per-server=8 \
  --split=8 \
  --min-split-size=10M \
  --disable-ipv6=true \
  --check-certificate=true \
  --content-disposition-default-utf8=true \
  --user-agent="Wget/1.12" \
  --quiet=true \
  --dir="/app/downloads" \
  --input-file=/dev/null \
  >/app/aria2.log 2>&1 &
