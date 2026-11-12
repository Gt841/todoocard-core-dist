#!/usr/bin/env bash
# 本地端到端验证（不启 BLE）：三资产 sha → 解压 → 归一化 → pip → apply.py → py_compile。
#
# 用法：
#   bash scripts/verify.sh                # 完整链路（含 pip install）
#   bash scripts/verify.sh --skip-pip     # 跳过 pip（离线/快速）
#   CACHE=/path bash scripts/verify.sh    # 自定义资产缓存目录
#
# 前置：scripts/build-extension.sh + scripts/build-manifest.sh 已跑过，
#       且 CACHE 里有 source.tar.gz 与 python-official.tar.gz。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="${CACHE:-/tmp/todoocard-dist-assets}"
SKIP_PIP=0
for arg in "$@"; do
  case "$arg" in
    --skip-pip) SKIP_PIP=1 ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

WORK="$(mktemp -d /tmp/todoocard-verify.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

sha256() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}';
  else sha256sum "$1" | awk '{print $1}'; fi
}
check_sha() {
  local actual
  actual="$(sha256 "$1")"
  if [[ "$actual" != "$2" ]]; then
    echo "FAIL  sha256 不符: $(basename "$1")" >&2
    echo "      manifest=$2" >&2
    echo "      actual  =$actual" >&2
    exit 1
  fi
  echo "  OK  $(basename "$1")  $actual"
}

echo "==> [0/7] 读取 manifest.json"
python3 - "$ROOT/manifest.json" <<'PY' > "$WORK/manifest.env"
import json, sys
from pathlib import Path
m = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
key = "darwin-arm64"
p = m["platforms"][key]
for name, value in [
    ("CORE_VERSION", m["coreVersion"]),
    ("CORE_COMMIT", m["coreCommit"]),
    ("CORE_TAG", m.get("coreTag", "")),
    ("SOURCE_SHA", p["sourceSha256"]),
    ("PY_SHA", p["pythonSha256"]),
    ("EXT_SHA", p["extensionSha256"]),
    ("SOURCE_URL", p["sourceUrl"]),
    ("PY_URL", p["pythonUrl"]),
    ("EXT_URL", p["extensionUrl"]),
]:
    print(f"{name}={value}")
PY
# shellcheck disable=SC1091
source "$WORK/manifest.env"
echo "    coreVersion=$CORE_VERSION  coreCommit=$CORE_COMMIT  展示 tag=$CORE_TAG"

echo "==> [1/7] 三资产 sha256 校验"
SOURCE="$CACHE/source.tar.gz"
PYARCHIVE="$CACHE/python-official.tar.gz"
EXT="$ROOT/dist/extension-$CORE_VERSION.zip"
for f in "$SOURCE" "$PYARCHIVE" "$EXT"; do
  [[ -f "$f" ]] || { echo "FAIL  缺少本地资产: $f" >&2; exit 1; }
done
check_sha "$SOURCE" "$SOURCE_SHA"
check_sha "$PYARCHIVE" "$PY_SHA"
check_sha "$EXT" "$EXT_SHA"

echo "==> [2/7] 解压"
mkdir -p "$WORK/src_raw" "$WORK/py_raw" "$WORK/stage"
tar -xzf "$SOURCE" -C "$WORK/src_raw"
tar -xzf "$PYARCHIVE" -C "$WORK/py_raw"
unzip -q "$EXT" -d "$WORK/stage/extension"

echo "==> [3/7] 归一化（模拟插件 normalizeSourceDir / normalizePythonDir）"
SRC_DIR="$WORK/src_raw/todoocard-eink-$CORE_COMMIT"
if [[ ! -d "$SRC_DIR" ]]; then
  echo "FAIL  源码顶层目录名与 coreCommit 不符，期望 todoocard-eink-$CORE_COMMIT" >&2
  echo "      实际: $(ls "$WORK/src_raw")" >&2
  exit 1
fi
mv "$SRC_DIR" "$WORK/stage/eink"
if [[ -d "$WORK/py_raw/python" ]]; then
  mv "$WORK/py_raw/python" "$WORK/stage/python"
else
  mv "$WORK/py_raw" "$WORK/stage/python"
fi
PY_BIN="$WORK/stage/python/bin/python3"
for f in "$WORK/stage/eink/server.py" "$WORK/stage/eink/requirements.txt" \
         "$WORK/stage/eink/sender.py" \
         "$WORK/stage/extension/apply.py" "$WORK/stage/extension/extension.json" \
         "$WORK/stage/extension/hotfixes/v1.0.11.json" "$PY_BIN"; do
  [[ -f "$f" ]] || { echo "FAIL  归一化后缺少: $f" >&2; exit 1; }
done
echo "  OK  stage/{eink,python,extension} 布局就绪"

echo "==> [4/7] pip install -r requirements.txt"
if [[ "$SKIP_PIP" == "1" ]]; then
  echo "  SKIP（--skip-pip）"
else
  "$PY_BIN" -m pip install -q -r "$WORK/stage/eink/requirements.txt"
  echo "  OK"
fi

echo "==> [5/7] 运行扩展补丁器"
"$PY_BIN" "$WORK/stage/extension/apply.py" "$WORK/stage/eink" \
  --core-version "$CORE_VERSION" --core-commit "$CORE_COMMIT"

echo "==> [6/7] py_compile 全量核心源码"
"$PY_BIN" -m py_compile "$WORK"/stage/eink/*.py
echo "  OK"

echo "==> [7/7] 注入结果断言"
"$PY_BIN" - "$WORK/stage/eink" <<'PY'
import sys
from pathlib import Path
eink = Path(sys.argv[1])
card = (eink / "card.py").read_text(encoding="utf-8")
server = (eink / "server.py").read_text(encoding="utf-8")
sender = (eink / "sender.py").read_text(encoding="utf-8")
checks = [
    ("force-python helper", "def _todoocard_force_python() -> bool:" in card),
    ("pair_python", "async def _pair_python(self, device_id: str) -> bool:" in card),
    ("3 个或门控", card.count("or _todoocard_force_python():") == 3),
    ("3 个配对门控", card.count("and _todoocard_force_python():") == 3),
    ("pick_folders 未改", '    def pick_folders(self) -> list[str]:\n        if sys.platform != "darwin":' in card),
    ("HOST 默认回环", 'HOST = os.environ.get("HOST", "127.0.0.1")' in server),
    ("TCPSite 用 HOST", "web.TCPSite(runner, HOST, PORT)" in server),
    ("旧 0.0.0.0 绑定已移除", 'web.TCPSite(runner, "0.0.0.0", PORT)' not in server),
    # v1.0.11 专属 hotfix
    ("WRITE_TIMEOUT 常量", "WRITE_TIMEOUT = 8.0" in sender),
    ("控制点写入全限时", "async def write_control(data: bytes, label: str) -> None:" in sender),
    ("0x01 不再裸写", "await client.write_gatt_char(control, bytes([CMD_REQ_BLOCK]), response=True)" not in sender),
    ("订阅通知限时", "asyncio.wait_for(client.start_notify" in sender),
    ("断连限时", "asyncio.wait_for(client.disconnect(), timeout=WRITE_TIMEOUT)" in sender),
    ("占位卡字号已修", 'R.FS["title"]' not in card),
    # 发送失败弹窗要显示真正原因，而不是 [sender] 日志开头
    ("超时错误映射成短句", "卡片没回应蓝牙指令" in card),
    ("兜底只取日志最后一行", "lines = [ln.strip() for ln in text.splitlines()" in card),
    # 精确绑定：两台卡广播名/厂商数据相同，绝不 fallback 到另一台
    ("已绑定只认精确 UUID", "已绑定 device_id 时" in sender),
    ("绑定的卡没出现就跳过", "if bound:\n            continue" in sender),
    ("日志标出 exact/fallback", "匹配={_match}" in sender),
    ("明确报没看到已绑定的卡", "没看到已绑定的卡片" in sender),
    ("后台自动配对也只认精确 UUID", "if bound and str(addr).upper() not in bound:" in card),
    ("绑定失败提示引导重新绑定", "没找到已绑定的那张卡" in card),
]
for label, ok in checks:
    print(f"  {'OK  ' if ok else 'FAIL'} {label}")
    if not ok:
        sys.exit(1)
PY

echo ""
echo "PASS  本地全链路验证通过（未启 BLE）。"
echo "      manifest 中的 extensionUrl（本脚本只校验本地 zip，不下载线上资产）："
echo "      $EXT_URL"
