#!/usr/bin/env bash
# 生成 v2 manifest.json：钉 commit sha + 三资产 sha256。
#
# 用法：
#   bash scripts/build-manifest.sh              # 复用 CACHE 里已下载的资产
#   REFRESH=1 bash scripts/build-manifest.sh   # 强制重新下载上游资产并复算 sha
#   CACHE=/path bash scripts/build-manifest.sh # 自定义资产缓存目录
#
# 前置：先跑 scripts/build-extension.sh 生成扩展 zip 与其 sha256。
# 注意：GitHub archive tarball 的字节可能随服务端重新生成而变化；发布前务必 REFRESH=1
#       重跑本脚本，并用 scripts/verify.sh 复核。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="${CACHE:-/tmp/todoocard-dist-assets}"
REFRESH="${REFRESH:-0}"
mkdir -p "$CACHE"

CORE_VERSION="${CORE_VERSION:-1.0.11}"
CORE_COMMIT="${CORE_COMMIT:-3642b4b25e42e38776f3227db601474173f915b1}"
CORE_TAG="${CORE_TAG:-v1.0.11-macos}"     # 仅展示/追溯，不参与下载
MANIFEST_VERSION="${MANIFEST_VERSION:-2.0.1}"   # 2.0.1 = 含 v1.0.11 专属 hotfix 的扩展包；coreVersion 仍是 1.0.11，需插件「强制重装」

SOURCE_URL="https://github.com/shidaifufen/todoocard-eink/archive/${CORE_COMMIT}.tar.gz"

PY_RELEASE="${PY_RELEASE:-20261110}"
PY_VERSION="${PY_VERSION:-3.11.18}"
PY_ARCH="${PY_ARCH:-aarch64-apple-darwin}"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_RELEASE}/cpython-${PY_VERSION}%2B${PY_RELEASE}-${PY_ARCH}-install_only.tar.gz"
PLATFORM_KEY="${PLATFORM_KEY:-darwin-arm64}"

EXT_ZIP="$ROOT/dist/extension-$CORE_VERSION.zip"
EXT_SHA_FILE="$EXT_ZIP.sha256"
if [[ ! -f "$EXT_ZIP" || ! -f "$EXT_SHA_FILE" ]]; then
  echo "缺少扩展包或 sha 文件，请先跑：bash scripts/build-extension.sh" >&2
  exit 1
fi

sha256() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}';
  else sha256sum "$1" | awk '{print $1}'; fi
}

echo "==> [1/3] 源码 tarball（按 commit sha 钉死）"
if [[ "$REFRESH" == "1" || ! -f "$CACHE/source.tar.gz" ]]; then
  curl -fLsS --retry 3 -o "$CACHE/source.tar.gz" "$SOURCE_URL"
fi
SOURCE_SHA="$(sha256 "$CACHE/source.tar.gz")"
echo "    $SOURCE_SHA"

echo "==> [2/3] 便携 Python（astral-sh 官方 install_only 原包）"
if [[ "$REFRESH" == "1" || ! -f "$CACHE/python-official.tar.gz" ]]; then
  curl -fLsS --retry 3 -o "$CACHE/python-official.tar.gz" "$PY_URL"
fi
PY_SHA="$(sha256 "$CACHE/python-official.tar.gz")"
echo "    $PY_SHA"

echo "==> [3/3] 扩展 zip + 写 manifest.json"
EXT_SHA="$(cat "$EXT_SHA_FILE")"
echo "    $EXT_SHA"

ROOT="$ROOT" CORE_VERSION="$CORE_VERSION" CORE_COMMIT="$CORE_COMMIT" \
CORE_TAG="$CORE_TAG" MANIFEST_VERSION="$MANIFEST_VERSION" \
SOURCE_URL="$SOURCE_URL" SOURCE_SHA="$SOURCE_SHA" \
PY_URL="$PY_URL" PY_SHA="$PY_SHA" PLATFORM_KEY="$PLATFORM_KEY" \
EXT_SHA="$EXT_SHA" python3 - <<'PY'
import json
import os
from pathlib import Path

e = os.environ
core_version = e["CORE_VERSION"]
manifest = {
    "version": e["MANIFEST_VERSION"],
    "coreVersion": core_version,
    "coreCommit": e["CORE_COMMIT"],
    "coreTag": e["CORE_TAG"],
    "platforms": {
        e["PLATFORM_KEY"]: {
            "sourceUrl": e["SOURCE_URL"],
            "sourceSha256": e["SOURCE_SHA"],
            "pythonUrl": e["PY_URL"],
            "pythonSha256": e["PY_SHA"],
            "extensionUrl": (
                "https://github.com/Gt841/todoocard-core-dist/releases/download/"
                f"v{core_version}/extension-{core_version}.zip"
            ),
            "extensionSha256": e["EXT_SHA"],
        }
    },
}
out = Path(e["ROOT"]) / "manifest.json"
out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"    {out}")
PY

echo "完成。extensionUrl 指向 GitHub Release；改完 manifest 需 push 到 main 让 Pages 生效。"
