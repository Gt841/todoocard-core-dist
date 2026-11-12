#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""todoocard-core-dist 扩展补丁器。

把「macOS 纯 Python 发送/配对 + 默认本机绑定」注入上游 todoocard-eink v1.0.11
源码（源码 tarball 里的松散 .py，不是 PyInstaller 冻结二进制）。

契约：
    python apply.py <eink_dir> --core-version <ver> --core-commit <sha>

    退出码 0 = 成功（含幂等无操作）；非 0 = 失败，安装器据此中止、旧核心完好。

守卫（任何一条不满足即失败，绝不静默打错补丁）：
    1. --core-version / --core-commit 必须与 extension.json 声明一致；
       整个扩展包只配套一个上游版本，其他版本直接拒绝、不执行；
    2. extension.json 的锚点 id 集合必须与本文件 PATCHES 一致；
    3. 每条改动先断言上游原文锚点在目标文件里「恰好出现 1 次」；
    4. 已注入标记存在则跳过（幂等）；
    5. 落盘前用 compile() 预检语法，落盘后用 py_compile 复核；
       任一编译失败则不写入任何文件；
    6. assets/ 下的静态资源在补丁全部成功后才安装到核心目录（不参与编译、幂等）。

版本专属 hotfix（hotfixes/v<coreVersion>.json）：
    除基础补丁外，按核心版本加载同名 hotfix 文件，并二次核对文件内的
    targetCoreVersion / targetCoreCommit。**任何其他版本或 commit 都不加载、
    不注入**，因此 v1.0.11 的热修复绝不会被误用到上游新版本上。上游发新版时
    必须另建 fixture 与锚点；若不为新版本提供 hotfix 文件，则仅执行基础补丁部分。
"""
from __future__ import annotations

import argparse
import json
import py_compile
import sys
from dataclasses import dataclass
from pathlib import Path


class PatchError(Exception):
    """扩展补丁失败的基类。"""


class AnchorError(PatchError):
    """上游源码漂移：锚点缺失、变形或出现多次。"""


class VersionError(PatchError):
    """扩展包与目标核心版本/commit 不匹配。"""


class CompileError(PatchError):
    """注入后的源码无法编译。"""


@dataclass(frozen=True)
class Patch:
    id: str
    file: str
    marker: str
    replacement: str


# replacement 用 raw 三引号字符串保存，内部的 \n、"…" 等按字面写入目标源码。
# 锚点（上游原文）不在这里，统一由 extension.json 的 anchors 提供。
PATCHES: tuple[Patch, ...] = (
    Patch(
        id="card-import-os",
        file="card.py",
        marker="import os  # TODOOCARD-FORCE-PYTHON",
        replacement=r'''import logging
import os  # TODOOCARD-FORCE-PYTHON
import random''',
    ),
    Patch(
        id="card-force-helper",
        file="card.py",
        marker="def _todoocard_force_python() -> bool:",
        replacement=r'''_LOGGER = logging.getLogger("todoocard")

# TODOOCARD-FORCE-PYTHON: macOS 纯 Python 门控（由 todoocard-core-dist 扩展注入）
def _todoocard_force_python() -> bool:
    """TODOOCARD_FORCE_PYTHON=1 时，macOS 也走 bleak 纯 Python 路径。"""
    return os.environ.get("TODOOCARD_FORCE_PYTHON") == "1"''',
    ),
    Patch(
        id="card-pair-python",
        file="card.py",
        marker="async def _pair_python(self, device_id: str) -> bool:",
        replacement=r'''    # TODOOCARD-FORCE-PYTHON: macOS 纯 Python 配对（检测窗口 → bleak 连接 → 系统配对）
    async def _pair_python(self, device_id: str) -> bool:
        """长按卡片进入配对窗口后，用 bleak 连接触发 macOS 系统配对。

        复用上游的 _scan_card（窗口检测）与 _pair_bleak（连接 / bonding），
        不依赖无授权 Swift 工具。
        """
        found = await asyncio.get_running_loop().run_in_executor(None, self._scan_card)
        addr = (found or {}).get("addr") or device_id
        if not found:
            self._pair_lines.append("[ble] 未扫到配对窗口，仍尝试直接连接（请长按卡片按钮 5 秒）")
        elif not found.get("pairing"):
            self._pair_lines.append("[ble] 卡片未在配对窗口，仍尝试直接连接")
        self._emit()
        return await self._pair_bleak(addr)

    def _scan_card(self) -> dict | None:''',
    ),
    Patch(
        id="card-gate-build-payload",
        file="card.py",
        marker='    def _build_payload(self, image_path: Path) -> dict:\n        if sys.platform != "darwin" or _todoocard_force_python():',
        replacement=r'''    def _build_payload(self, image_path: Path) -> dict:
        if sys.platform != "darwin" or _todoocard_force_python():  # TODOOCARD-FORCE-PYTHON''',
    ),
    Patch(
        id="card-gate-send-blocking",
        file="card.py",
        marker='    def _send_blocking(self, image_path: Path, wait_sec: float | None = None) -> dict:\n        if sys.platform != "darwin" or _todoocard_force_python():',
        replacement=r'''    def _send_blocking(self, image_path: Path, wait_sec: float | None = None) -> dict:
        if sys.platform != "darwin" or _todoocard_force_python():  # TODOOCARD-FORCE-PYTHON''',
    ),
    Patch(
        id="card-gate-scan",
        file="card.py",
        marker='    async def _scan(request):\n        svc = current()\n        if sys.platform != "darwin" or _todoocard_force_python():',
        replacement=r'''    async def _scan(request):
        svc = current()
        if sys.platform != "darwin" or _todoocard_force_python():  # TODOOCARD-FORCE-PYTHON''',
    ),
    Patch(
        id="card-gate-pair-session",
        file="card.py",
        marker="ok = await self._pair_python(dev)",
        replacement=r'''        async def _run():
            try:
                if sys.platform == "darwin" and _todoocard_force_python():  # TODOOCARD-FORCE-PYTHON
                    ok = await self._pair_python(dev)
                    self._pair_state = "success" if ok else "fail"
                    if ok:
                        await self._drain_outbox()
                    return
                if sys.platform != "darwin":
                    ok = await self._pair_bleak(dev)''',
    ),
    Patch(
        id="card-gate-run-pair",
        file="card.py",
        marker="return await self._pair_python(device_id)",
        replacement=r'''    async def _run_pair(self, device_id: str) -> bool:
        if sys.platform == "darwin" and _todoocard_force_python():  # TODOOCARD-FORCE-PYTHON
            return await self._pair_python(device_id)
        if sys.platform != "darwin":''',
    ),
    Patch(
        id="card-gate-pair-api",
        file="card.py",
        marker="ok = await svc._pair_python(str(dev))",
        replacement=r'''            if sys.platform == "darwin" and _todoocard_force_python():  # TODOOCARD-FORCE-PYTHON
                ok = await svc._pair_python(str(dev))
                return web.json_response({"ok": ok, "code": 0 if ok else 1,
                                          "output": "\n".join(svc._pair_lines[-40:])})
            if sys.platform != "darwin":
                ok = await svc._pair_bleak(str(dev))''',
    ),
    Patch(
        id="server-host-bind",
        file="server.py",
        marker='HOST = os.environ.get("HOST", "127.0.0.1")',
        replacement=r'''PORT = int(os.environ.get("PORT", "8199"))
HOST = os.environ.get("HOST", "127.0.0.1")  # TODOOCARD-FORCE-PYTHON: 默认仅本机回环''',
    ),
    Patch(
        id="server-tcpsite",
        file="server.py",
        marker="web.TCPSite(runner, HOST, PORT)",
        replacement=r'''    site = web.TCPSite(runner, HOST, PORT)  # TODOOCARD-FORCE-PYTHON''',
    ),
)


def load_extension(ext_path: Path) -> dict:
    if not ext_path.is_file():
        raise PatchError(f"找不到 extension.json: {ext_path}")
    try:
        return json.loads(ext_path.read_bytes().decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise PatchError(f"extension.json 解析失败: {e}") from e


HOTFIX_DIR = Path(__file__).with_name("hotfixes")
ASSETS_DIR = Path(__file__).with_name("assets")


def install_assets(eink_dir: Path) -> list[str]:
    """把扩展包里的静态资源装进核心目录（2.0.4：web/devices.html 多设备登记页）。

    不在 patch 体系内：HTML 不参与 compile/py_compile，只在源码补丁全部落盘、
    编译复核成功之后才复制。assets/ 不存在就跳过，旧扩展包与未来新版本不受影响；
    内容一致时不重复写（幂等）。
    """
    if not ASSETS_DIR.is_dir():
        return []
    logs: list[str] = []
    for src in sorted(ASSETS_DIR.rglob("*")):
        if not src.is_file() or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(ASSETS_DIR)
        dst = eink_dir / rel
        data = src.read_bytes()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_file() and dst.read_bytes() == data:
            logs.append(f"资源已存在 {rel}（幂等）")
        else:
            dst.write_bytes(data)
            logs.append(f"安装资源 {rel}")
    return logs


def load_hotfix(
    core_version: str, core_commit: str, hotfix_dir: Path | None = None
) -> tuple[dict | None, str]:
    """按「版本文件名 + 精确 commit」加载专属 hotfix。

    只认 hotfixes/v<coreVersion>.json。文件缺失、版本不符、commit 不符时返回
    (None, 说明)，调用方跳过注入——保证 1.0.11 的热修复不会带到其他上游版本。
    """
    directory = hotfix_dir or HOTFIX_DIR
    path = directory / f"v{core_version}.json"
    if not path.is_file():
        return None, f"跳过 hotfix：{path.name} 不存在（v1.0.11 专属补丁不适用于 v{core_version}）"
    try:
        hf = json.loads(path.read_bytes().decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise PatchError(f"hotfix 文件解析失败 {path}: {e}") from e
    if not isinstance(hf, dict):
        raise PatchError(f"hotfix 文件格式错误: {path}")
    if hf.get("targetCoreVersion") != core_version:
        return None, "跳过 hotfix：targetCoreVersion 与传入版本不一致"
    if hf.get("targetCoreCommit") != core_commit:
        return None, "跳过 hotfix：targetCoreCommit 与传入 commit 不一致（上游可能已漂移）"

    patches = hf.get("patches")
    if not isinstance(patches, list) or not patches:
        raise PatchError(f"hotfix 缺少 patches: {path}")
    seen: set[str] = set()
    for p in patches:
        if not isinstance(p, dict) or not all(
            isinstance(p.get(k), str) for k in ("id", "file", "marker")
        ):
            raise PatchError(f"hotfix patch 字段不完整: {path}")
        if not isinstance(p.get("lines"), list) or not isinstance(p.get("replacement"), list):
            raise PatchError(f"hotfix patch {p['id']} 缺少 lines/replacement 数组")
        if p["id"] in seen:
            raise PatchError(f"hotfix patch id 重复: {p['id']}")
        seen.add(p["id"])
    return hf, f"应用 hotfix {hf.get('id', path.stem)}（{len(patches)} 条，仅 v{core_version}）"


def apply_extension(
    eink_dir: Path,
    core_version: str,
    core_commit: str,
    ext_path: Path | None = None,
    hotfix_dir: Path | None = None,
) -> list[str]:
    """把扩展注入 eink_dir，返回逐条日志；失败抛 PatchError 且不改动任何文件。"""
    ext_path = ext_path or Path(__file__).with_name("extension.json")
    ext = load_extension(ext_path)

    # 整个扩展包绑定单一上游版本：其他版本直接拒绝，不执行任何注入。
    if core_version != ext.get("targetCoreVersion"):
        raise VersionError(
            f"coreVersion 不匹配：传入 {core_version}，扩展要求 {ext.get('targetCoreVersion')}"
        )
    if core_commit != ext.get("targetCoreCommit"):
        raise VersionError(
            f"coreCommit 不匹配：传入 {core_commit}，扩展要求 {ext.get('targetCoreCommit')}（上游可能已漂移）"
        )

    anchors = {a.get("id"): a for a in ext.get("anchors", [])}
    expected = {p.id for p in PATCHES}
    if set(anchors) != expected or None in anchors:
        missing = sorted(expected - set(anchors))
        extra = sorted(set(anchors) - expected)
        raise PatchError(f"extension.json 锚点清单与 apply.py 不一致：缺 {missing}，多 {extra}")

    for patch in PATCHES:
        if anchors[patch.id].get("file") != patch.file:
            raise PatchError(f"锚点 {patch.id} 的目标文件声明不一致")
        if not isinstance(anchors[patch.id].get("lines"), list):
            raise PatchError(f"锚点 {patch.id} 缺少 lines")

    hotfix, hotfix_note = load_hotfix(core_version, core_commit, hotfix_dir)
    hotfix_patches: list[dict] = hotfix["patches"] if hotfix else []

    files = {"card.py", "server.py"} | {p["file"] for p in hotfix_patches}
    contents: dict[str, str] = {}
    for name in sorted(files):
        target = eink_dir / name
        if not target.is_file():
            raise PatchError(f"目标目录缺少 {name}：{eink_dir}")
        try:
            contents[name] = target.read_bytes().decode("utf-8")
        except UnicodeDecodeError as e:
            raise PatchError(f"{name} 不是 UTF-8 文本: {e}") from e

    log: list[str] = [hotfix_note]

    # 基础补丁
    for patch in PATCHES:
        text = contents[patch.file]
        if patch.marker in text:
            log.append(f"跳过 {patch.id}（已注入，幂等）")
            continue
        anchor = "\n".join(anchors[patch.id]["lines"])
        count = text.count(anchor)
        if count != 1:
            raise AnchorError(
                f"锚点 {patch.id} 在 {patch.file} 中应恰好出现 1 次，实际 {count} 次；"
                "上游源码可能已漂移，请维护者重基扩展包"
            )
        contents[patch.file] = text.replace(anchor, patch.replacement, 1)
        log.append(f"注入 {patch.id}")

    # 版本专属 hotfix：与基础补丁同一套锚点/幂等守卫
    for hp in hotfix_patches:
        name = hp["file"]
        text = contents[name]
        if hp["marker"] in text:
            log.append(f"跳过 hotfix {hp['id']}（已注入，幂等）")
            continue
        anchor = "\n".join(hp["lines"])
        count = text.count(anchor)
        if count != 1:
            raise AnchorError(
                f"hotfix 锚点 {hp['id']} 在 {name} 中应恰好出现 1 次，实际 {count} 次；"
                "上游源码可能已漂移，该版本专属补丁不注入"
            )
        contents[name] = text.replace(anchor, "\n".join(hp["replacement"]), 1)
        log.append(f"注入 hotfix {hp['id']}")

    # 落盘前语法预检：任何编译失败都不写入，避免留下半成品核心。
    for name, text in contents.items():
        try:
            compile(text, str(eink_dir / name), "exec")
        except SyntaxError as e:
            raise CompileError(f"{name} 注入后语法错误（第 {e.lineno} 行）: {e.msg}") from e

    for name, text in contents.items():
        (eink_dir / name).write_bytes(text.encode("utf-8"))

    # 落盘后按契约再做一次 py_compile 复核。
    for name in contents:
        try:
            py_compile.compile(str(eink_dir / name), doraise=True)
        except py_compile.PyCompileError as e:
            raise CompileError(f"{name} py_compile 失败: {e}") from e

    # 静态资源只在所有源码补丁都成功落盘、编译复核之后才安装。
    log.extend(install_assets(eink_dir))
    return log


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="todoocard-core-dist 扩展补丁器")
    ap.add_argument("eink_dir", help="已归一化的上游核心源码目录（根含 server.py）")
    ap.add_argument("--core-version", required=True, help="manifest.coreVersion")
    ap.add_argument("--core-commit", required=True, help="manifest.coreCommit")
    ap.add_argument("--extension-json", default=None, help="默认取 apply.py 同目录的 extension.json")
    ap.add_argument("--hotfix-dir", default=None, help="默认取 apply.py 同目录的 hotfixes/（测试用）")
    args = ap.parse_args(argv)

    try:
        ext_path = Path(args.extension_json) if args.extension_json else None
        hf_dir = Path(args.hotfix_dir) if args.hotfix_dir else None
        lines = apply_extension(
            Path(args.eink_dir), args.core_version, args.core_commit, ext_path, hf_dir
        )
        for line in lines:
            print(line)
        print("扩展补丁完成")
        return 0
    except PatchError as e:
        print(f"扩展补丁失败（上游版本可能已漂移）: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
