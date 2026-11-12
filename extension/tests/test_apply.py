# -*- coding: utf-8 -*-
"""扩展补丁器测试（Python 标准库 unittest，无第三方依赖）。

用真实上游 v1.0.11 源码 fixture，不 mock 被测文本逻辑。
    python3 -m unittest discover -s extension/tests -v
"""
from __future__ import annotations

import ast
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXT_DIR = HERE.parent
APPLY = EXT_DIR / "apply.py"
EXT_JSON = EXT_DIR / "extension.json"
HOTFIX_JSON = EXT_DIR / "hotfixes" / "v1.0.11.json"
FIXTURE = HERE / "fixtures" / "v1.0.11"
FILES = ("card.py", "server.py", "sender.py")

CORE_VERSION = "1.0.11"
CORE_COMMIT = "3642b4b25e42e38776f3227db601474173f915b1"


def load_apply_module():
    spec = importlib.util.spec_from_file_location("todoocard_apply", APPLY)
    mod = importlib.util.module_from_spec(spec)
    # dataclass 在解析注解时会回查 sys.modules，动态加载必须先注册。
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(spec.name, None)
    return mod


def run_apply(eink_dir: Path, version: str = CORE_VERSION,
              commit: str = CORE_COMMIT, ext_json: Path | None = None,
              hotfix_dir: Path | None = None):
    cmd = [sys.executable, str(APPLY), str(eink_dir),
           "--core-version", version, "--core-commit", commit]
    if ext_json is not None:
        cmd += ["--extension-json", str(ext_json)]
    if hotfix_dir is not None:
        cmd += ["--hotfix-dir", str(hotfix_dir)]
    return subprocess.run(cmd, capture_output=True, text=True)


class ApplyPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="todoocard-apply-")
        self.eink = Path(self.tmp.name) / "eink"
        self.eink.mkdir()
        for name in FILES:
            shutil.copyfile(FIXTURE / name, self.eink / name)
        self.before = {n: (self.eink / n).read_bytes() for n in FILES}

    def tearDown(self):
        self.tmp.cleanup()

    def text(self, name: str) -> str:
        return (self.eink / name).read_bytes().decode("utf-8")

    def assert_untouched(self):
        for name, original in self.before.items():
            self.assertEqual((self.eink / name).read_bytes(), original,
                             f"{name} 被意外改动")

    def test_00_anchors_unique_on_real_fixture(self):
        """基础锚点与 1.0.11 hotfix 锚点在真实上游源码里各恰好出现 1 次。"""
        ext = json.loads(EXT_JSON.read_bytes().decode("utf-8"))
        for a in ext["anchors"]:
            anchor = "\n".join(a["lines"])
            with self.subTest(anchor=a["id"]):
                self.assertEqual(
                    (FIXTURE / a["file"]).read_bytes().decode("utf-8").count(anchor), 1,
                    f"{a['id']} 锚点不唯一或不存在（上游漂移？）",
                )
        hf = json.loads(HOTFIX_JSON.read_bytes().decode("utf-8"))
        for p in hf["patches"]:
            anchor = "\n".join(p["lines"])
            src = (FIXTURE / p["file"]).read_bytes().decode("utf-8")
            with self.subTest(hotfix=p["id"]):
                self.assertEqual(src.count(anchor), 1)
                self.assertEqual(src.count(p["marker"]), 0,
                                 "marker 不能出现在未打补丁的上游原文里")

    def test_01_real_source_success(self):
        """真实 v1.0.11 fixture → 基础改动 + hotfix 全部注入、语法编译通过。"""
        r = run_apply(self.eink)
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")
        card = self.text("card.py")
        server = self.text("server.py")

        self.assertIn("import os  # TODOOCARD-FORCE-PYTHON", card)
        self.assertIn("def _todoocard_force_python() -> bool:", card)
        self.assertIn("async def _pair_python(self, device_id: str) -> bool:", card)
        self.assertIn("return await self._pair_bleak(addr)", card)

        # 3 处「或」门控 + 3 处「darwin 且 force」配对门控
        self.assertEqual(card.count('or _todoocard_force_python():'), 3)
        self.assertEqual(card.count('and _todoocard_force_python():'), 3)
        self.assertIn("ok = await self._pair_python(dev)", card)
        self.assertIn("return await self._pair_python(device_id)", card)
        self.assertIn("ok = await svc._pair_python(str(dev))", card)

        # 上游已修的东西不重复注入，pick_folders 的平台分支保持原样
        self.assertIn("async def _pair_bleak(self, device_id: str) -> bool:", card)
        self.assertIn(
            '    def pick_folders(self) -> list[str]:\n        if sys.platform != "darwin":',
            card,
        )
        self.assertNotIn("def _scan_python", card)

        self.assertIn('HOST = os.environ.get("HOST", "127.0.0.1")', server)
        self.assertIn("web.TCPSite(runner, HOST, PORT)", server)
        self.assertNotIn('web.TCPSite(runner, "0.0.0.0", PORT)', server)

        for name in FILES:
            compile(self.text(name), name, "exec")

    def test_02_drift_fails_without_writing(self):
        """上游锚点漂移 → 非 0 + 中文错误，且不落盘半成品。"""
        card = self.text("card.py")
        drifted = card.replace(
            '    def _send_blocking(self, image_path: Path, wait_sec: float | None = None) -> dict:\n'
            '        if sys.platform != "darwin":',
            '    def _send_blocking(self, image_path: Path, wait_sec: float | None = None) -> dict:\n'
            '        if sys.platform == "win32":',
            1,
        )
        self.assertNotEqual(card, drifted)
        (self.eink / "card.py").write_bytes(drifted.encode("utf-8"))

        r = run_apply(self.eink)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("锚点", r.stderr + r.stdout)
        self.assertIn("漂移", r.stderr + r.stdout)
        self.assertEqual((self.eink / "card.py").read_bytes(), drifted.encode("utf-8"))
        for name in ("server.py", "sender.py"):
            self.assertEqual((self.eink / name).read_bytes(), self.before[name])

    def test_03_idempotent(self):
        """连跑两次：第二次全部跳过，三个文件字节完全一致。"""
        r1 = run_apply(self.eink)
        self.assertEqual(r1.returncode, 0, r1.stderr)
        after_first = {n: (self.eink / n).read_bytes() for n in FILES}
        r2 = run_apply(self.eink)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("跳过 hotfix", r2.stdout)
        self.assertIn("跳过 hotfix sender-control-writes", r2.stdout)
        for name in after_first:
            self.assertEqual((self.eink / name).read_bytes(), after_first[name],
                             f"{name} 第二次运行被改动了")

    def test_04_version_and_commit_mismatch(self):
        """coreVersion / coreCommit 任一不符 → 非 0，且不改动源码。"""
        cases = [
            ("9.9.9", CORE_COMMIT, "coreVersion"),
            (CORE_VERSION, "deadbeef", "coreCommit"),
        ]
        for version, commit, expect in cases:
            with self.subTest(version=version, commit=commit):
                r = run_apply(self.eink, version=version, commit=commit)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(expect, r.stderr + r.stdout)
                self.assert_untouched()

    def test_05_tampered_anchor_json_fails(self):
        """篡改 extension.json 的锚点文本 → 断言失败，非 0。"""
        ext = json.loads(EXT_JSON.read_bytes().decode("utf-8"))
        for a in ext["anchors"]:
            if a["id"] == "card-gate-scan":
                a["lines"][1] = "        svc = current()  # drifted"
        bad = Path(self.tmp.name) / "bad-extension.json"
        bad.write_text(json.dumps(ext, ensure_ascii=False), encoding="utf-8")

        r = run_apply(self.eink, ext_json=bad)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("锚点", r.stderr + r.stdout)
        self.assert_untouched()

    def test_06_missing_server_py_fails(self):
        """缺 server.py → 非 0，提示清晰。"""
        (self.eink / "server.py").unlink()
        r = run_apply(self.eink)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("server.py", r.stderr + r.stdout)

    # ── v1.0.11 专属 hotfix ──────────────────────────────────────────────

    def test_07_hotfix_applies_write_timeouts_and_font_fix(self):
        """hotfix 生效：BLE 每次 await 都限时，占位卡不再引用 R.FS 字典。"""
        r = run_apply(self.eink)
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")
        self.assertIn("应用 hotfix v1.0.11-hotfix-1", r.stdout)
        self.assertEqual(r.stdout.count("注入 hotfix "), 8)

        sender = self.text("sender.py")
        card = self.text("card.py")

        self.assertIn("WRITE_TIMEOUT = 8.0", sender)
        self.assertIn("async def write_control(data: bytes, label: str) -> None:", sender)
        self.assertIn('await write_control(bytes([CMD_REQ_BLOCK]), "block size")', sender)
        self.assertIn('"payload 长度",', sender)
        self.assertIn('await write_control(bytes([CMD_START]), "开始传输")', sender)
        self.assertIn("asyncio.wait_for(client.start_notify", sender)
        self.assertIn("asyncio.wait_for(client.disconnect(), timeout=WRITE_TIMEOUT)", sender)
        # 所有 write_gatt_char 都必须被 wait_for 或 write_control 包住
        self.assertNotIn(
            "await client.write_gatt_char(control, bytes([CMD_REQ_BLOCK]), response=True)",
            sender,
        )
        self.assertNotIn(
            "                        await client.write_gatt_char(data_ch, packet, response=True)",
            sender,
        )
        self.assertGreaterEqual(sender.count("await asyncio.wait_for("), 3)

        self.assertNotIn('R.FS["title"]', card)
        self.assertIn('font=_font("bold", 36), fill=WHITE', card)
        compile(sender, "sender.py", "exec")

    def test_08_hotfix_never_applies_to_other_versions(self):
        """版本门控：其他版本 / 别的 commit / 无 hotfix 文件 → 一律不注入 sender.py。"""
        mod = load_apply_module()
        cases = [
            ("1.0.12", CORE_COMMIT, None, HOTFIX_JSON.parent),
            ("1.0.11", "deadbeef" * 5, None, HOTFIX_JSON.parent),
            (CORE_VERSION, CORE_COMMIT, None, Path(self.tmp.name) / "empty"),
        ]
        for version, commit, _, directory in cases:
            with self.subTest(version=version, commit=commit, directory=directory):
                directory.mkdir(parents=True, exist_ok=True)
                hf, note = mod.load_hotfix(version, commit, directory)
                self.assertIsNone(hf)
                self.assertIn("跳过 hotfix", note)

        # 端到端：1.0.11 + 正确 commit，但显式给一个空 hotfix 目录 →
        # 基础补丁照常，sender.py 一个字节都不动。
        empty = Path(self.tmp.name) / "empty"
        r = run_apply(self.eink, hotfix_dir=empty)
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")
        self.assertIn("跳过 hotfix", r.stdout)
        self.assertEqual((self.eink / "sender.py").read_bytes(), self.before["sender.py"])
        self.assertNotEqual((self.eink / "card.py").read_bytes(), self.before["card.py"])

        # 非 1.0.11 版本连基础补丁也拒绝执行（先恢复未打补丁的源码）
        for name in FILES:
            shutil.copyfile(FIXTURE / name, self.eink / name)
        r2 = run_apply(self.eink, version="1.0.12")
        self.assertNotEqual(r2.returncode, 0)
        self.assert_untouched()

    def test_09_hotfix_anchor_drift_fails_without_writing(self):
        """hotfix 锚点漂移 → 非 0，且三个文件都不落盘。"""
        sender = self.text("sender.py")
        drifted = sender.replace(
            "        await client.write_gatt_char(control, bytes([CMD_REQ_BLOCK]), response=True)",
            "        await client.write_gatt_char(control, bytes([CMD_REQ_BLOCK]), response=False)",
            1,
        )
        self.assertNotEqual(sender, drifted)
        (self.eink / "sender.py").write_bytes(drifted.encode("utf-8"))

        r = run_apply(self.eink)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("hotfix 锚点", r.stderr + r.stdout)
        self.assertEqual((self.eink / "sender.py").read_bytes(), drifted.encode("utf-8"))
        for name in ("card.py", "server.py"):
            self.assertEqual((self.eink / name).read_bytes(), self.before[name])

    def test_10_calling_without_sender_py_fails(self):
        """hotfix 生效时缺 sender.py → 非 0（跳过 hotfix 时则不要求该文件）。"""
        (self.eink / "sender.py").unlink()
        r = run_apply(self.eink)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sender.py", r.stderr + r.stdout)


    def test_11_friendly_error_shows_real_reason(self):
        """发送失败弹窗必须显示真正原因，而不是 [sender] 日志的开头。

        直接把打过补丁的 card.py 里的 _friendly_error 单独 exec 出来调用，
        避免 import 整个 card.py（它依赖 Pillow / aiohttp 等运行时库）。
        """
        r = run_apply(self.eink)
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")

        tree = ast.parse(self.text("card.py"))
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "_friendly_error")
        ns: dict = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]),
                     "<friendly_error>", "exec"), ns)
        friendly = ns["_friendly_error"]

        timeout_log = "\n".join([
            "[sender] payload 197711 bytes, target=519D2FA1-CB32-3C08-C409-EB8EB66DAAE1",
            "[sender] 等广播（总预算 180s）…",
            "[sender] 看到卡片：TodooCard",
            "[sender] 请求 block size",
            "block size 控制点写入 8s 无响应（设备未进入接收窗口？）",
        ])
        msg = friendly(timeout_log)
        self.assertIn("长按背面按钮", msg)
        self.assertNotIn("[sender]", msg)
        self.assertLessEqual(len(msg), 120, "弹窗 slice(0,120) 必须能完整显示")

        # 未识别的多行日志 → 只给最后一行，前端 slice(0,120) 也不会截错
        self.assertEqual(
            friendly("[sender] 第一行日志\n[sender] 第二行日志\n真正的失败原因在这里"),
            "真正的失败原因在这里",
        )
        # 已有的友好映射不能被破坏
        self.assertIn("长按卡片背面按钮唤醒", friendly("没扫到卡片"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
