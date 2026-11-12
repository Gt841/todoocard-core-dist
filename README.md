# todoocard-core-dist

`plugin-todoocard` 的**版本匹配扩展包 + manifest 托管仓库**。

> 状态（2026-11-12）：**已上线**。远端仓库 `Gt841/todoocard-core-dist`、Release `v1.0.11`、
> GitHub Pages 均已发布；`manifest.json` 的 `extensionUrl` 可公开下载。
> 上游更新时的完整工作流见 [docs/maintainer.md](docs/maintainer.md)。

## 为什么独立

上游 `shidaifufen/todoocard-eink` 更新时，**只动这个仓库**（重做扩展、复算 sha、更新 manifest、发 Release/Pages），插件仓库一行不改。插件只认设置里的 `manifestUrl`。

## 分发模型

| 资产 | 内容 | 托管 | 谁维护 |
| --- | --- | --- | --- |
| 上游源码 tarball | 松散 `.py`（可打补丁） | GitHub archive，**按 commit sha 钉死** | 上游 |
| 便携 Python | astral-sh `install_only` 官方原包 | python-build-standalone Releases | 上游 |
| `extension-<ver>.zip` | `apply.py` + `extension.json` + `tests/` | 本仓库 GitHub Releases | **我们** |
| `manifest.json` | v2 schema：钉版本 + 三资产 URL/sha | 本仓库 GitHub Pages | **我们** |

上游 Release 里的便携包是 PyInstaller 冻结二进制（零散 `.py` 为 0），**不能打补丁**，所以核心一律用源码 tarball。

## 钉版本机制（三重守卫）

上游源码里没有 `__version__`，且**不存在 `v1.0.11` tag**（只有 `v1.0.11-macos` / `v1.0.11-windows`）。因此：

1. `coreCommit` 钉死 commit sha → `sourceUrl = .../archive/<sha>.tar.gz`；`coreTag` **仅作展示/追溯**。
2. `sourceSha256` 锁定 tarball 字节；解压后顶层目录必须是 `todoocard-eink-<sha>/`。
3. `apply.py` 逐条断言上游原文锚点在目标文件里恰好出现 1 次，并核对 `coreVersion` + `coreCommit`；漂移即非 0 退出，安装器中止、旧核心完好。

两个 v1.0.11 tag 的 `card.py` / `server.py` / `sender.py` / `requirements.txt` blob 完全相同，锚点只需一套。

## 扩展注入了什么

| 改动 | 原因 |
| --- | --- |
| `import os` + `_todoocard_force_python()` | 上游 `card.py` 无 `import os`，门控需要读 env |
| 3 处 `if sys.platform != "darwin" or _todoocard_force_python():` | `_build_payload` / `_send_blocking` / `_scan`（Web UI 扫描）在 `TODOOCARD_FORCE_PYTHON=1` 时走 bleak 纯 Python |
| `_pair_python` + 3 处配对门控 | macOS 配对改走「`_scan_card` 检测窗口 → 复用上游 `_pair_bleak` 连接/系统配对」，不依赖无授权 Swift 工具 |
| `HOST` 默认 `127.0.0.1` + `TCPSite(runner, HOST, PORT)` | 核心 Web UI 无鉴权；`HOST=0.0.0.0` 可显式恢复局域网访问 |

**不注入**：`_scan_python`（上游 `_scan_card` 与 `_scan` 的 bleak 分支已自包含）、sender 的 `find_device_by_address` 修复、`_send_python` 的 `output` 键修复（上游 v1.0.11 已修）、`pick_folders` 的平台分支（文件夹选择器，非 BLE 路径）。

## 版本专属 hotfix（只配套 v1.0.11）

`extension/hotfixes/v1.0.11.json` 是**按核心版本隔离**的热修复，2026-11-12 真机故障后补上：

| 修复 | 原因 |
| --- | --- |
| `sender.py` 所有控制点写入、通知订阅、数据块写入、断连统一套 `asyncio.wait_for(..., WRITE_TIMEOUT=8s)` | macOS CoreBluetooth 的带响应写在设备不回 ATT 响应时会**永久挂起**，导致 `card.py:send()` 的 `finally` 不执行、`busy` 永久为 true，之后所有发送被 409 挡掉 |
| `card.py` 占位卡 `R.FS["title"]` → `36` | `card_render` 的 `FS` 是 float 缩放因子、不是字号字典，照片文件夹为空时 `/api/card/preview?kind=photo` 必 500 |
| `card.py` `_friendly_error` 新增超时映射 + 兜底只取最后一行 | 上游 `text[-300:]` 把整段 `[sender]` 日志写进 `history.message`，前端 `slice(0,120)` 又截的是**开头**，用户只看到「payload 197711 bytes…等广播」，真正的失败原因被吞掉 |

**「其他版本不执行」是代码级保证**：`apply.py` 只加载 `hotfixes/v<coreVersion>.json`，再逐字段核对文件内的 `targetCoreVersion` / `targetCoreCommit`；文件名、版本、commit 任一不符即跳过、不注入。整个扩展包本身也只声明 `1.0.11` + 固定 commit，其他版本在全局断言处直接拒绝。上游发新版时必须另建 fixture、锚点与（如需要）新的 `v<ver>.json`，**不要复用 v1.0.11 的 hotfix**。

## 目录

```
extension/apply.py            文本补丁器（锚点断言 + 幂等 + compile/py_compile + 失败不落盘 + 版本专属 hotfix）
extension/extension.json      targetCoreVersion / targetCoreCommit / 11 条锚点
extension/hotfixes/           v<coreVersion>.json：按版本+commit 双重门控的热修复（当前 v1.0.11-hotfix-1，8 条）
extension/tests/              unittest：真实 fixture / 漂移 / 幂等 / 版本不符 / hotfix 门控 / 缺文件
scripts/build-extension.sh    打 extension-<ver>.zip + sha256
scripts/build-manifest.sh     拉三资产算 sha → manifest.json（REFRESH=1 强制重下）
scripts/verify.sh             本地端到端（不启 BLE）
manifest.json                 v2
docs/maintainer.md            上游更新工作流
```

## 本地验证

```bash
python3 -m unittest discover -s extension/tests -v
bash scripts/build-extension.sh
bash scripts/build-manifest.sh            # 复用缓存；REFRESH=1 重新下载复算
bash scripts/verify.sh --skip-pip         # 完整链路去掉 --skip-pip
```

`verify.sh` 会校验三资产 sha、归一化（剥 `todoocard-eink-<sha>/` 与 `python/` 顶层）、跑 `apply.py`、编译全部顶层 `.py`、断言注入结果。

> 上游 `server.py` 的 `"/{name:scenes\.html}"` 会触发 Python 的 `SyntaxWarning: invalid escape sequence '\.'`，这是上游原有代码，非扩展引入，不影响编译与运行。

## 线上端点（已发布）

| 用途 | 地址 |
| --- | --- |
| manifest（Pages，插件默认 `manifestUrl`） | `https://gt841.github.io/todoocard-core-dist/manifest.json` |
| 扩展包（Release 资产） | `https://github.com/Gt841/todoocard-core-dist/releases/download/v1.0.11/extension-1.0.11.zip` |
| 仓库 | `https://github.com/Gt841/todoocard-core-dist` |

Pages 托管来源为 `main` 分支根目录；仓库根放 `.nojekyll`，避免 Jekyll 改写 `manifest.json`。
**更新 manifest 只需 push 到 `main`**，等 Pages 重新构建即可，插件仓库不用动。

> **热修复（manifest `version: 2.0.2`）**：扩展包内容更新了，但 `coreVersion` 仍是 `1.0.11`；
> 插件按 `coreVersion` 比较版本，会显示「已是最新版本」。已装过核心的用户必须在控制台点
> **「强制重装」** 才会拉到带 hotfix 的扩展包——重装流程会自动停核心、下载、打补丁、原子替换并重启。
> `2.0.2` 相对 `2.0.1` 只补了「发送失败弹窗显示不出真正原因」：`_friendly_error` 现在把超时
> 映射成可操作短句，未识别的报错也只给日志最后一行。前端 `web/card.html` 的 `slice(0,120)`
> 仍会截开头，但短句能完整显示；本机若手动改过前端，重装后以后端短句为准。

仍待人工完成：真机 BLE 全链路验证、插件发版 / 思源集市 PR（见 `../plugin-todoocard/docs/real-machine-validation.md`）。

## License

`extension/tests/fixtures/v1.0.11/` 下的上游源码遵循其 MIT LICENSE（见同目录 `LICENSE`）。本仓库脚本与补丁器为维护者自有代码。
