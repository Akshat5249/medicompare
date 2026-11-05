#!/usr/bin/env bash
# Downloads NPPA's therapeutic-category ceiling price lists into data/downloads/.
# NPPA's copyright policy permits free reproduction when accurate and acknowledged:
# https://nppa.gov.in/en/copyrightpolicy (verified 2026-11-05)
set -euo pipefail
cd "$(dirname "$0")/../downloads"
base="https://nppa.gov.in/storage/uploads/pdf"
for file in \
  2845-fb-posts-anti-cancer-e3f335bfae6294a35741b326d91a26a5.pdf \
  2845-fb-posts-anti-diabetes-a2491c25ce7e20c9200884e1f92cf68a.pdf \
  2845-fb-posts-anti-hiv-834be8c8fdb7b0dce18e87266ca05512.pdf \
  2845-fb-posts-anti-tb-4767550580d2ed15f1877932bd47e39a.pdf \
  2845-fb-posts-cardio-ea1e3eda2076b6367cf9a9685da62f95.pdf; do
  curl --fail --silent --show-error --location --max-time 120 --output "$file" "$base/$file"
  echo "downloaded $file"
done
shasum -a 256 ./*.pdf
