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
| `sender.py` / `card.py` 精确绑定（6 条） | 现场两台 TodooCard 广播名都是 `TodooCard`、厂商数据都是 `4c 11 b9 01 13`，上游 `_scan_once` / `_scan_card` 的 fallback 会挑 `devs.items()` 里第一个（RSSI 强的先出现），造成「唤醒 A、去连 B」。已绑定时只认精确 UUID，扫不到就明确报错并引导重新绑定；`device_id` 支持逗号分隔多个 UUID，日志标 `匹配=exact/fallback` |
| `card.py` 多设备别名登记（8 条）+ 静态管理页 | 多台卡片用自定义别名管理，人工登记 MAC 与一组 macOS UUID；切换别名时把 UUID 集合写回 `device_id`，注册表另存到思源工作区随其自带备份同步（详见下节） |
| 原生控制台内联增强（2.0.5，`assets/web/todoocard-devices.js`） | 把登记别名做进「设备与配对」的扫描/「用这台」流程；登记 ≥2 台时发送前弹「发到哪张卡？」手动选目标，只有 1 台则不弹选择。幂等内联进 `web/card.html`，不动 22 条补丁、不加后端路由 |
| `sender.py` 握手兜底（2.0.6） | 真机：连上、订阅通知都成功，但写 `0x01` 查块大小 **8s 没有 ATT 响应**。CoreBluetooth 一条连接只允许一个未完成的 ATT 请求，卡住后原地重试无效——改成「带响应写 2.5s 不回执 → 改用 Write Command → 还不行断开重连」，45s 内多轮重试；日志打出控制点/数据点属性、协商 MTU、读 FEF3 链路自检 |

## 多设备支持（2.0.4 / 2.0.5）

电脑旁放两台以上 TodooCard 时，上游按广播顺序挑设备会「唤醒 A、去连 B」。2.0.4 引入
**别名注册表**：给每张卡起一个自定义别名，把「别名 ↔ 蓝牙 MAC ↔ 一组 macOS UUID」人工登记下来，
发送时只认当前别名登记过的 UUID，绝不连到别的卡。2.0.5 把登记入口和发送选择做进原生控制台。

### 原生控制台：配对时登记别名 / 发送时选设备（2.0.5）

2.0.4 的登记能力只在独立页 `/devices`，原生「设备与配对」页仍只能「用这台」裸绑 UUID，
发送也不问目标。2.0.5 由 `apply.py:install_assets()` 把一段自包含 JS **幂等内联进上游
`web/card.html`**（固定 id 的 `<script>` 块，内容比对后整块更新），刷新控制台即可用：

| 场景 | 行为 |
| --- | --- |
| 「设备与配对」→ 扫描附近设备 | 改走 `/api/card/devices/scan` 结构化结果，每台标注「已登记 / 未登记」，多出「填入登记」按钮 |
| 扫描结果点「用这台」 | 登记表单填了别名 → 一步完成「绑定 UUID + 登记别名 + 设为当前」；没填则保留上游裸绑定，并把 UUID 自动填进表单引导登记 |
| 不扫描直接登记 | 表单 UUID 留空时自动取当前已绑定的 `device_id`，方便给老绑定补起名字 |
| 点「发送这个模板」/ 每日计划「执行」 | 登记 **≥2 台** 才弹「发到哪张卡？」手动选择，选中后按别名切换当前目标再发送；**只有 1 台或未登记时不弹窗，直接发送** |
| 定时推送 / 按键唤醒自动推送 | 后端自动执行，不弹窗，发到当前选中的卡 |
| 已登记列表 | 「设为当前」「删除」「从思源备份重新载入」以及通往 `/devices` 的入口都在同一页 |

选中后会把该别名登记过的所有 UUID 写回 `device_id`，复用 2.0.3 的精确匹配，
绝不 fallback 到另一台卡。选**内联而非外链**是因为上游 `server.py` 只静态服务
`card.html` / `scenes.html`，内联无需新增后端路由；`card.html` 缺失或 `</body>` 不唯一时
`apply.py` 直接失败，绝不静默丢功能。后端没有 2.0.4 接口时脚本降级：不弹选择、登记区提示升级，
原有单卡流程不受影响。

### 打开管理页

核心启动后访问 `http://127.0.0.1:8199/devices`：

1. 点「扫描 8 秒」，长按卡片背面按钮 5 秒唤醒要登记的那台；
2. 在扫描结果里点「填入」拿到它的 macOS UUID；
3. 填**别名**（如 `客厅卡`）和**蓝牙 MAC**（小程序显示的 `FFFF99803616`，即 `FF:FF:99:80:36:16`）；
4. 点「登记」，勾「设为当前」即立刻生效；换卡时在「已登记的卡片」里点「设为当前」。

扫描结果会标注「已登记 / 未登记」。macOS 的 peripheral UUID 会随配对或系统变化，出现新的
未登记 UUID 时用「归到此别名」追加即可，不用重新填 MAC。

### 数据结构

`card.json` 新增两个字段；**不登记任何别名时，行为与旧版单卡 `device_id` 完全一致**：

```json
{
  "device_alias": "客厅卡",
  "device_id": "519D2FA1-…,C3B1E61E-…",
  "device_name": "客厅卡 | FF:FF:99:80:36:16",
  "devices": [
    {"alias": "客厅卡", "mac": "FF:FF:99:80:36:16", "name": "TodoCard | FFFF99803616",
     "uuids": ["519D2FA1-CB32-3C08-C409-EB8EB66DAAE1"]}
  ]
}
```

切换别名时，核心把该别名登记过的所有 UUID 逗号拼接写回 `device_id`，复用 2.0.3 的精确匹配；
`send()` / `_scan_card()` / 配对流程等上游代码完全不用改。

### 随思源备份同步

核心目录刻意放在思源 `data/` **外面**（否则思源同步会覆盖核心程序），所以 `card.json`
不在思源备份范围内。注册表另存一份到思源工作区：

```
<SiYuan>/data/plugins/plugin-todoocard/todoocard-devices.json
```

- 位于 `data/` 内 → **直接用思源自带的备份 / 同步**带走，不需要另做云同步；
- 核心启动时同步文件优先覆盖本地 `card.json`；每次配置落盘都原子写回同步文件；
- 恢复备份或换机后，在管理页点「从思源备份重新载入」即可还原，不用重启核心；
- 路径可用环境变量 `TODOOCARD_DEVICES_FILE` 覆盖；定位不到 `data/` 或写入失败只告警，不影响本地功能。

**注意**：同步的是别名 / MAC / UUID 集合。UUID 是每台 Mac 本地生成的，换机后很可能不同，
用「归到此别名」追加新 UUID 即可；两台机器同时改动时由思源自己的冲突处理决定。

### API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/devices` | 多设备登记页（`assets/web/devices.html` 由 `apply.py` 装进核心 `web/`） |
| GET | `/api/card/devices` | 注册表 / 当前别名 / 同步文件路径与状态 |
| POST | `/api/card/devices/scan` | 结构化蓝牙扫描，标注每个 UUID 的归属别名 |
| POST | `/api/card/devices/register` | 人工登记（同 MAC 或同别名合并，UUID 去重） |
| POST | `/api/card/devices/select` | 按别名切换当前卡片 |
| POST | `/api/card/devices/adopt` | 把轮换后的新 UUID 追加到某别名 |
| POST | `/api/card/devices/reload` | 从思源备份同步文件重新载入 |
| POST | `/api/card/devices/remove` | 删除一个别名 |

**「其他版本不执行」是代码级保证**：`apply.py` 只加载 `hotfixes/v<coreVersion>.json`，再逐字段核对文件内的 `targetCoreVersion` / `targetCoreCommit`；文件名、版本、commit 任一不符即跳过、不注入。整个扩展包本身也只声明 `1.0.11` + 固定 commit，其他版本在全局断言处直接拒绝。上游发新版时必须另建 fixture、锚点与（如需要）新的 `v<ver>.json`，**不要复用 v1.0.11 的 hotfix**。

## 目录

```
extension/apply.py            文本补丁器（锚点断言 + 幂等 + compile/py_compile + 失败不落盘 + 版本专属 hotfix + 静态资源安装 + 控制台脚本内联）
extension/extension.json      targetCoreVersion / targetCoreCommit / 11 条锚点
extension/hotfixes/           v<coreVersion>.json：按版本+commit 双重门控的热修复（当前 v1.0.11-hotfix-1，21 条）
extension/assets/web/         devices.html：多设备登记页；todoocard-devices.js：控制台增强脚本（两者由 apply.py 装进核心 web/，后者另内联进 card.html）
extension/tests/              unittest：真实 fixture / 漂移 / 幂等 / 版本不符 / hotfix 门控 / 精确绑定 / 注册表 / 备份同步 / 控制台内联
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

> **热修复（manifest `version: 2.0.6`）**：扩展包内容更新了，但 `coreVersion` 仍是 `1.0.11`；
> 插件按 `coreVersion` 比较版本，会显示「已是最新版本」。已装过核心的用户必须在控制台点
> **「强制重装」** 才会拉到带 hotfix 的扩展包——重装流程会自动停核心、下载、打补丁、原子替换并重启。
> `2.0.6` 修**真机发送失败**：连上后写控制点 `0x01` 等不到 ATT 响应（macOS 日志 8s 超时）。
> 现在带响应写不通就改 Write Command，再不行断开重连重试，45 秒内反复试；发送时请长按卡片
> 背面按钮 5 秒让它进接收窗口。`coreVersion` 不变，因此每次内容更新都必须「强制重装」才生效。

仍待人工完成：真机 BLE 全链路验证、插件发版 / 思源集市 PR（见 `../plugin-todoocard/docs/real-machine-validation.md`）。

## License

`extension/tests/fixtures/v1.0.11/` 下的上游源码遵循其 MIT LICENSE（见同目录 `LICENSE`）。本仓库脚本与补丁器为维护者自有代码。
