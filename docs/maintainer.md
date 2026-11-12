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
- [ ] `python3 -m unittest discover -s extension/tests -v` 全绿。
- [ ] `verify.sh` 的 8 条注入断言全 OK。

## 上游发新 tag 时（只动本仓库）

假设上游发到 `v1.0.12`：

1. **取新源码**：`git ls-remote --tags origin` 找真实 tag（注意上游习惯用 `vX.Y.Z-macos` / `vX.Y.Z-windows`，未必有裸 `vX.Y.Z`）；`git rev-parse <tag>` 拿 commit sha；下载 `https://github.com/shidaifufen/todoocard-eink/archive/<sha>.tar.gz`。
2. **比对核心文件**：`card.py` / `server.py` / `sender.py` / `requirements.txt` 与上版 blob 差异；判断我们注入的改动哪些上游已自行修好（要删对应 patch），哪些仍需注入。
3. **重基锚点**：把新源码放进 `extension/tests/fixtures/<ver>/`，逐条更新 `extension.json` 的 `anchors.lines`；跑 `test_00_anchors_unique_on_real_fixture` 确认每条恰好 1 次；必要时调整 `apply.py` 的 replacement。旧版 fixture 保留，用于漂移回归。
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

## manifest v2 schema

```json
{
  "version": "2.0.0",
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
- 扩展 zip 的根必须直接是 `apply.py` / `extension.json` / `tests/`，安装器检查「解压后根有 `apply.py`」。
- macOS 纯 Python env `TODOOCARD_FORCE_PYTHON=1` 由插件 `buildCoreEnv` 传播；`HOST` 也由插件继承环境变量（`HOST=0.0.0.0` 会重新暴露无鉴权界面，仅在可信网络使用）。
