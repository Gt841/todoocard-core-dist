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
`v1.0.11.json`（`v1.0.11-hotfix-1`，22 条）：给 `sender.py` 的所有 BLE await 套
`asyncio.wait_for(..., WRITE_TIMEOUT=8s)`，修 `card.py` 占位卡的 `R.FS["title"]`，
让 `_friendly_error` 把超时错误翻译成可操作短句、其余未识别报错只取日志最后一行，
精确绑定 6 条，以及多设备别名登记 / 思源备份同步 8 条（见下）。

**精确绑定（2.0.3）**：现场两台 TodooCard 的广播名都是 `TodooCard`、厂商数据都是
`4c 11 b9 01 13`，上游 `_scan_once` / `_scan_card` 的 fallback 会按 `devs.items()`
顺序挑第一台（RSSI 强的先出现），造成「唤醒 A、去连 B」。现在只要 `device_id` 非空，
就只接受精确 UUID 命中，另一台一律跳过；扫不到就报「没看到已绑定的卡片」并引导重新
扫描绑定。`device_id` 支持逗号分隔多个 UUID（macOS peripheral UUID 会轮换），
日志会打出 `匹配=exact/fallback` 和真实 UUID。未绑定时保留兜底发现，首次选卡仍可用。
**注意**：macOS BLE 广播里没有 MAC，UUID 变化后必须人工重新绑定，无法自动反推设备真身。

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
exec 出来实测超时/多行日志/已知错误三种输出）、`test_12`（用假 bleak 注入两台同名卡，
实测「另一台先出现也只认绑定卡」「绑定的卡没出现就返回 None」「未绑定仍可兜底」「多 UUID 命中」）、
`test_13`（绑定失败提示是短句、日志标 exact/fallback、后台自动配对也不许连错卡）、
`test_14`（同文件 marker 互不相交，防止幂等误判）、`test_15`（登记/合并/去重/别名切换/
思源备份文件写入与换机恢复，直接 exec 注入的模块级函数）、`test_16`（静态页安装且幂等、API 与同步钩子齐全）、
`test_17`（控制台脚本内联、幂等、换版本整块更新、功能点齐全）、`test_18`（card.html 漂移/缺失直接失败）。

## 多设备别名登记与思源备份（2.0.4）

- `card.json` 增 `device_alias` / `devices`；`save_cfg` 白名单放行，`status()` 暴露给前端。
- 切换别名时把该别名登记过的 UUID 逗号拼接写回 `device_id`，复用 2.0.3 精确匹配，
  **上游 send()/_scan_card()/pair 一行都不用改**；不登记别名时单卡行为不变。
- 管理页 `assets/web/devices.html` 由 `apply.py:install_assets()` 在补丁全部成功后装到
  核心 `web/`（不参与 compile/py_compile，内容一致时不重复写）。构建脚本必须把 `assets/` 打进 zip。
- 核心目录在思源 `data/` 外面（否则会被思源同步覆盖），注册表因此另存一份到
  `<SiYuan>/data/plugins/plugin-todoocard/todoocard-devices.json`，靠思源自带备份/同步带走。
  启动时同步文件优先；`_save_cfg()` 每次原子写回；`/api/card/devices/reload` 用于换机恢复。
  环境变量 `TODOOCARD_DEVICES_FILE` 可覆盖路径。
- MAC 只能人工登记（macOS BLE 广播无 MAC、GATT `0x2A25` 读超时）；UUID 轮换后用
  `/api/card/devices/adopt` 追加。两台机器同时改动由思源自己的冲突处理决定。
- **marker 防撞**：apply.py 按「文件内是否已有 marker」判幂等，所以同文件内任一 marker
  都不得出现在其他补丁的 replacement 文本里，`test_14` 专门守这条。


## 原生控制台内联增强（2.0.5）

2.0.4 的登记能力只在独立页 `/devices`，用户实际用的是原生 `web/card.html` 的「设备与配对」页
（只有「用这台」裸绑 UUID）和「发送这个模板」按钮（不问目标）。2.0.5 补上这两处：

- `assets/web/todoocard-devices.js` 由 `install_assets()` 复制到核心 `web/`，并**内联进
  `web/card.html` 的 `</body>` 前**（固定 id `todoocard-devices-inline` 的 `<script>` 块）。
  按块内容比对：相同则跳过（幂等），不同则整块替换（未来改 JS 无需新锚点）。
- 包装 `scanDevices`（改走结构化 `/api/card/devices/scan`，结果标注归属、加「填入登记」）、
  `useDevice`（填了别名就一步 register+select，否则保留上游绑定并引导登记）、
  `send` / `runNow`（登记 ≥2 台时弹选择器 → `/api/card/devices/select` → 再调原函数；
  0/1 台不弹窗）。定时与按键唤醒的自动推送是后端行为，不拦。
- 上游 `server.py` 只静态服务 `card.html` / `scenes.html`，所以选内联而非外链，
  **不改 22 条 hotfix、不加后端路由、不动 server.py**。
- `card.html` 缺失或 `</body>` 不唯一 → `inject_console_script()` 抛 `PatchError`，
  安装器据此中止，绝不静默丢掉功能；脚本内含 `</script` 字面量也直接拒绝注入。
- 后端无 2.0.4 接口时全部降级（`/api/card/devices` 拿不到 → 不弹选择、登记区提示升级）。
- 验证：`node --check` 语法 + Node 最小 DOM mock 冒烟（1 台直发 / 2 台弹选择 / 取消不发送 /
  配对一步登记 / 扫描填入登记）+ `test_17` / `test_18` + `verify.sh` 12 条前端断言。

**发布注意**：hotfix 只改扩展包内容，`coreVersion` 不变，插件按 `coreVersion` 比较会判定
「已是最新」。已装用户必须点控制台的**「强制重装」**；manifest 的 `version`（`2.0.0` →
`2.0.1` → `2.0.2` → `2.0.3` → `2.0.4` → `2.0.5`）仅作为内容标识，不参与更新判定。

## manifest v2 schema

```json
{
  "version": "2.0.5",
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
