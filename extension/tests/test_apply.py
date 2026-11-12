# -*- coding: utf-8 -*-
"""扩展补丁器测试（Python 标准库 unittest，无第三方依赖）。

用真实上游 v1.0.11 源码 fixture，不 mock 被测文本逻辑。
    python3 -m unittest discover -s extension/tests -v
"""
from __future__ import annotations

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
FIXTURE = HERE / "fixtures" / "v1.0.11"

CORE_VERSION = "1.0.11"
CORE_COMMIT = "3642b4b25e42e38776f3227db601474173f915b1"


def run_apply(eink_dir: Path, version: str = CORE_VERSION,
              commit: str = CORE_COMMIT, ext_json: Path | None = None):
    cmd = [sys.executable, str(APPLY), str(eink_dir),
           "--core-version", version, "--core-commit", commit]
    if ext_json is not None:
        cmd += ["--extension-json", str(ext_json)]
    return subprocess.run(cmd, capture_output=True, text=True)


class ApplyPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="todoocard-apply-")
        self.eink = Path(self.tmp.name) / "eink"
        self.eink.mkdir()
        for name in ("card.py", "server.py"):
            shutil.copyfile(FIXTURE / name, self.eink / name)
        self.before = {n: (self.eink / n).read_bytes()
                       for n in ("card.py", "server.py")}

    def tearDown(self):
        self.tmp.cleanup()

    def text(self, name: str) -> str:
        return (self.eink / name).read_bytes().decode("utf-8")

    def test_00_anchors_unique_on_real_fixture(self):
        """每条锚点必须在真实上游源码里恰好出现 1 次（锚点清单自检）。"""
        ext = json.loads(EXT_JSON.read_bytes().decode("utf-8"))
        for a in ext["anchors"]:
            anchor = "\n".join(a["lines"])
            with self.subTest(anchor=a["id"]):
                self.assertEqual(
                    (FIXTURE / a["file"]).read_bytes().decode("utf-8").count(anchor), 1,
                    f"{a['id']} 锚点不唯一或不存在（上游漂移？）",
                )

    def test_01_real_source_success(self):
        """真实 v1.0.11 fixture → 全部改动注入 + 语法编译通过。"""
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

        # 注入后的文件能被 Python 编译（apply.py 内部已做，这里再独立验一次）
        compile(card, "card.py", "exec")
        compile(server, "server.py", "exec")

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
        # 失败时任何文件都不应被写入
        self.assertEqual((self.eink / "card.py").read_bytes(), drifted.encode("utf-8"))
        self.assertEqual((self.eink / "server.py").read_bytes(), self.before["server.py"])

    def test_03_idempotent(self):
        """连跑两次：第二次全部跳过，文件字节完全一致。"""
        r1 = run_apply(self.eink)
        self.assertEqual(r1.returncode, 0, r1.stderr)
        after_first = {n: (self.eink / n).read_bytes()
                       for n in ("card.py", "server.py")}
        r2 = run_apply(self.eink)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("跳过", r2.stdout)
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
                for name, original in self.before.items():
                    self.assertEqual((self.eink / name).read_bytes(), original)

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
        for name, original in self.before.items():
            self.assertEqual((self.eink / name).read_bytes(), original)

    def test_06_missing_server_py_fails(self):
        """缺 server.py → 非 0，提示清晰。"""
        (self.eink / "server.py").unlink()
        r = run_apply(self.eink)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("server.py", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
