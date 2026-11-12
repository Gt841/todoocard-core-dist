# fixture：上游 todoocard-eink v1.0.11 真实源码

来源：`https://github.com/shidaifufen/todoocard-eink/archive/3642b4b25e42e38776f3227db601474173f915b1.tar.gz`
（展示 tag：`v1.0.11-macos`；上游**没有**裸 `v1.0.11` tag）

- tarball sha256：`6afea74358af29ed3fe160560b9b409f030ab3aae25d485166617e8ed076cdd9`
- 解包顶层：`todoocard-eink-3642b4b25e42e38776f3227db601474173f915b1/`
- `card.py` 2181 行、`server.py` 74 行；与 `git rev-parse HEAD:card.py` / `HEAD:server.py` blob 一致（已逐文件核对）。
- 只取补丁器涉及的 `card.py` / `server.py` + `LICENSE`，供 `test_apply.py` 做**真实源码**测试（不 mock 文本逻辑）。
- 上游源码为 MIT，LICENSE 一并附带。

漂移动/新版本回归时，把新版同类文件放到 `fixtures/<ver>/`，并更新 `extension.json` 的锚点清单；旧 fixture 保留作回归对照。
