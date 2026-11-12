# 维护者工作流

面向 `Gt841/todoocard-core-dist`。**上游更新只动本仓库，插件仓库零改动。**

## 首次发布 v1.0.11（2026-11-12 已完成）

| # | 动作 | 命令 / 位置 | 授权 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 本地验证 | `python3 -m unittest discover -s extension/tests -v` | 否 | 已执行，7/7 |
| 2 | 构建扩展包 | `bash scripts/build-extension.sh` → `dist/extension-1.0.11.zip` | 否 | 已执行 |
| 3 | 生成 manifest | `REFRESH=1 bash scripts/build-manifest.sh` | 否（需联网） | 已执行，sha 复算无变化 |
| 4 | 端到端复核 | `bash scripts/verify.sh`（含 pip） | 否 | 已执行，8 条断言全绿 |
| 5 | 建仓库 + push | `Gt841/todoocard-core-dist` | 是 | 已完成 |
| 6 | 发 Release `v1.0.11` | 上传 `dist/extension-1.0.11.zip` | 是 | 已完成 |
| 7 | 开 GitHub Pages | `main` 分支根目录，`.nojekyll` | 是 | 已完成 |
| 8 | 插件默认 manifestUrl | `https://gt841.github.io/todoocard-core-dist/manifest.json` | 是 | 已完成 |

发布前核对清单：

- [ ] `manifest.json` 的 `sourceUrl` 含 40 位 commit sha，**不是** `tags/v1.0.11`（上游无此 tag）。
- [ ] `coreTag` 只作展示，不参与下载或校验。
- [ ] `sourceSha256` / `pythonSha256` / `extensionSha256` 与本地三资产逐一一致（`verify.sh` 会拦截）。
- [ ] `extension.json` 的 `targetCoreVersion` / `targetCoreCommit` 与 manifest 一致。
- [ ] `apply.py` 用**真实上游源码 tarball**跑通（不是 git clone 的工作树、更不是冻结二进制）。
- [ ] `python3 -m unittest discover -s extension/tests -v` 全绿（含 hotfix 门控用例）。
- [ ] `verify.sh` 的基础 + hotfix 注入断言全 OK。
- [ ] `extension/hotfixes/v<coreVersion>.json` 的 `targetCoreCommit` 与 manifest 一致；扩展 zip 根含 `hotfixes/`。

## 上游发新 tag 时（只动本仓库）

假设上游发到 `v1.0.12`：

1. **取新源码**：`git ls-remote --tags origin` 找真实 tag（注意上游习惯用 `vX.Y.Z-macos` / `vX.Y.Z-windows`，未必有裸 `vX.Y.Z`）；`git rev-parse <tag>` 拿 commit sha；下载 `https://github.com/shidaifufen/todoocard-eink/archive/<sha>.tar.gz`。
2. **比对核心文件**：`card.py` / `server.py` / `sender.py` / `requirements.txt` 与上版 blob 差异；判断我们注入的改动哪些上游已自行修好（要删对应 patch），哪些仍需注入。
3. **重基锚点**：把新源码放进 `extension/tests/fixtures/<ver>/`，逐条更新 `extension.json` 的 `anchors.lines`；跑 `test_00_anchors_unique_on_real_fixture` 确认每条恰好 1 次；必要时调整 `apply.py` 的 replacement。旧版 fixture 保留，用于漂移回归。**不要复用 `hotfixes/v1.0.11.json`**：apply.py 只按 `v<coreVersion>.json` 找文件，新版本默认不加载；若新版也需要修，另建同名版本文件并写对 `targetCoreCommit`。
4. **改版本号**：`extension.json` 的 `extensionVersion` / `targetCoreVersion` / `targetCoreCommit` / `sourceTag` / `sourceUrl` / `sourceSha256`；`build-manifest.sh` 的 `CORE_VERSION` / `CORE_COMMIT` / `CORE_TAG` 默认值。
5. **重建 + 验证**：`build-extension.sh` → `REFRESH=1 build-manifest.sh` → `verify.sh` → 全量测试。
6. **发布**：发 Release `v1.0.12`（上传新 zip）→ 推 `manifest.json` 到 Pages。**插件仓库不动**；用户下次点控制台「安装/更新」即自动采用新核心 + 匹配扩展。

## 锚点漂移的兜底语义

`apply.py` 遇到「锚点缺失 / 变形 / 出现多次」或「`coreVersion` / `coreCommit` 不符」时：

- 返回非 0，stderr 输出中文「扩展补丁失败（上游版本可能已漂移）」；
- **不写入任何文件**（落盘前先 `compile()` 预检，全部通过才一次性写入）；
- 插件安装器据此中止，`atomicReplaceDir` 还没执行，**旧核心完好**；
- 控制台提示维护者重基扩展包。

绝不静默打错补丁。

## 版本专属 hotfix

`extension/hotfixes/v<coreVersion>.json` 存放只对该上游版本成立的修复。当前只有
`v1.0.11.json`（`v1.0.11-hotfix-1`，8 条）：给 `sender.py` 的所有 BLE await 套
`asyncio.wait_for(..., WRITE_TIMEOUT=8s)`，修 `card.py` 占位卡的 `R.FS["title"]`，
并让 `_friendly_error` 把超时错误翻译成可操作短句、其余未识别报错只取日志最后一行
（否则「发送失败」弹窗只显示 `[sender] payload … 等广播` 这种日志开头，看不到原因）。

触发原因（2026-11-12 真机）：macOS CoreBluetooth 的 `write_gatt_char(..., response=True)`
在卡片不回 ATT Write Response 时会永远挂起，`sender.send()` 不返回 → `card.py:send()` 的
`finally: self._busy = False` 永不执行 → `/api/card` 的 `busy` 永久为 true → 后续发送全部 409。
现象是「点发送没任何反应」，日志最后一行停在 `[sender] 请求 block size`。

门控语义（**其他版本不执行**）：

1. `apply.py` 只拼 `hotfixes/v<coreVersion>.json`，文件不存在即跳过；
2. 加载后再核对文件内 `targetCoreVersion` 与 `targetCoreCommit`，任一不符即跳过；
3. 整个扩展包的 `extension.json` 也只声明 `1.0.11` + 固定 commit，其他版本在全局断言处直接拒绝；
4. hotfix 每条同样走「锚点恰好 1 次 / marker 幂等 / 编译预检」，漂移即非 0 且不落盘。

测试：`test_07`（注入与编译）、`test_08`（其他版本/其他 commit/空目录都不注入）、
`test_09`（锚点漂移）、`test_10`（缺 sender.py）、`test_11`（把 `_friendly_error` 单独
exec 出来实测超时/多行日志/已知错误三种输出）。

**发布注意**：hotfix 只改扩展包内容，`coreVersion` 不变，插件按 `coreVersion` 比较会判定
「已是最新」。已装用户必须点控制台的**「强制重装」**；manifest 的 `version`（`2.0.0` →
`2.0.1` → `2.0.2`）仅作为内容标识，不参与更新判定。

## manifest v2 schema

```json
{
  "version": "2.0.2",
  "coreVersion": "1.0.11",
  "coreCommit": "3642b4b25e42e38776f3227db601474173f915b1",
  "coreTag": "v1.0.11-macos",
  "platforms": {
    "darwin-arm64": {
      "sourceUrl": ".../archive/<sha>.tar.gz",
      "sourceSha256": "...",
      "pythonUrl": ".../cpython-...-install_only.tar.gz",
      "pythonSha256": "...",
      "extensionUrl": ".../releases/download/v1.0.11/extension-1.0.11.zip",
      "extensionSha256": "...",
      "depsUrl": "（可选）离线 wheels",
      "depsSha256": "（可选）"
    }
  }
}
```

平台键沿用插件 `platformKey()`：`darwin-arm64` / `darwin-x64` / `windows-x64` / `linux-x64`。新增平台时，源码 tarball 可共用同一 commit sha（上游源码跨平台一致），只需换对应架构的便携 Python URL 与 sha。

## 风险备忘

- **GitHub archive tarball 字节可能随服务端重新生成而变化** → 发布前必须 `REFRESH=1` 复算 `sourceSha256`；用户侧 sha 不符即中止，不会装错。
- 便携 Python 官方 `install_only` 解压顶层是 `python/` → 插件 `normalizePythonDir` 会剥一层；**不要**像旧 dev-kit 那样重打包成 flat。
- 上游 `server.py` 的 `scenes\.html` 有 `SyntaxWarning`，是上游原有写法，非扩展引入。
- macOS 被插件强制 `TODOOCARD_FORCE_PYTHON=1` 走 bleak 纯 Python 发送（原本主要面向 Win/Linux）；CoreBluetooth 的带响应写可能挂起，靠 hotfix 的 `WRITE_TIMEOUT` 兜底。真实墨水屏能否刷成功仍需真机验证。
- 扩展 zip 的根必须直接是 `apply.py` / `extension.json` / `tests/`，安装器检查「解压后根有 `apply.py`」。
- macOS 纯 Python env `TODOOCARD_FORCE_PYTHON=1` 由插件 `buildCoreEnv` 传播；`HOST` 也由插件继承环境变量（`HOST=0.0.0.0` 会重新暴露无鉴权界面，仅在可信网络使用）。
