#!/usr/bin/env bash
# 把 extension/ 打成发布用 zip，并输出 sha256。
# 用法：bash scripts/build-extension.sh [VERSION]
# 产物：dist/extension-<ver>.zip + dist/extension-<ver>.zip.sha256
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="${1:-$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["extensionVersion"])' "$ROOT/extension/extension.json")}"
OUT="$ROOT/dist"
ZIP="$OUT/extension-$VER.zip"

mkdir -p "$OUT"
rm -f "$ZIP" "$ZIP.sha256"

# zip 根即 apply.py / extension.json / hotfixes/ / tests/ / assets/，
# 与安装器「解压后缺 apply.py 即中止」的约定一致；hotfixes/ 与 assets/ 必须随包分发
# （apply.py 会把 assets/ 下的静态页复制到核心 web/ 目录）。
( cd "$ROOT/extension" && zip -q -r "$ZIP" apply.py extension.json hotfixes tests assets \
    -x '*/__pycache__/*' '*.pyc' )

if command -v shasum >/dev/null 2>&1; then
  SHA="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
else
  SHA="$(sha256sum "$ZIP" | awk '{print $1}')"
fi
printf '%s\n' "$SHA" > "$ZIP.sha256"

echo "扩展包：$ZIP"
echo "sha256：$SHA"
echo "条目："
unzip -Z1 "$ZIP" | sed 's/^/  /'
