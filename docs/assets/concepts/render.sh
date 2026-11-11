#!/usr/bin/env bash
# 从 Mermaid 源文件重建网页使用的 SVG。需要 Node.js 和 Chrome/Chromium。
set -euo pipefail
cd "$(dirname "$0")"

for source in *.mmd; do
  npm exec --yes --package @mermaid-js/mermaid-cli@12.2.0 -- mmdc \
    -i "$source" -o "${source%.mmd}.svg" \
    -c mermaid-config.json -b '#101a35' --size 900
done
