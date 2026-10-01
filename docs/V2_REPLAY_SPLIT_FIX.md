# V2 通用回放加载器 split 隔离修复记录

最终独立覆盖发现 `EvaluatorReplay(root, oracle_access=True)` 原先会 eager 读取 cold_start、evolution、dev 和 sealed 输入，并解码共享文件中的全部隐藏标签及未来观察。API evolution 虽未把 sealed 字段送给 Agent、未评分 sealed，其加载行为仍违反封存隔离。此文独立记录修复；不会把没有送给模型当作没有读过文件。

## 最终行为与接口

内容负责人只修改 `tools/content/replay.py`、手工测试及本部分文档；Agent 负责人同步修改 `api_evolution.py` 调用方。Git 由总负责人统一提交。

```python
replay = EvaluatorReplay(
    "content_v1", oracle_access=True,
    allowed_splits={"evolution"}, case_ids={"opaque-requested-root"},
)
```

`oracle_access=True` 仍是 evaluator-only 的必要条件，不等于授予全部 split。`allowed_splits` 默认 `{cold_start}`；合法集合成员为 cold_start、evolution、dev、sealed_test，空/未知集合和单个字符串拒绝。dev 和 sealed_test 必须分别显式授予，普通 evolution 不打开这两个目录的 case 文件。`case_ids` 可进一步限制具体根，未登记或属于其他范围的根在读取任何 oracle 前拒绝；空根集合不打开任何内容文件。

共享的 oracle/labels.jsonl 和 observations.jsonl 仍按文本行扫描。`read_selected_jsonl(path, identities, key="case_id")` 在 opaque identity 上先筛选原行，之后才调用 JSON decoder，因此 out-of-scope 标签/观察 payload 不被解析或存入环境。所有 ID 沿用本包不含 JSON escape 的稳定 opaque string 规范。该修复不宣称共享文件的字节完全不可见；真正线上部署仍应只复制 `export_public` 的公开 bundle。

已加载案例必须与授予文件 split 一致，重复根拒绝；标签只按已加载 case_id 解码；观察只按这些标签 `branches[].reveal` 中实际出现的 observation_id 解码，缺失标签/观察拒绝启动。原来的授权、分支可达性、重复幂等和反馈到达门槛保持原逻辑。

API 的 `_evaluation_cases` 同步使用原行筛选 helper，而不再先解码全部 labels 再筛根。其 evolution 回放构造器显式传递 allowed_splits={evolution} 和请求 case_ids；GEPA 的独立 dev selection 仍只解析选择根的标签，不能把 dev/sealed 任意合并到 evolution 环境。

## 实际验收

新增 `tests/content/test_replay_split_isolation.py`，使用四个手工微型根及非法 JSON 哨兵，没有读取真实 content_v1 封存案例/标签，没有用合成 LLM 替代模型实测。

| 验收 | 证据 |
|---|---|
| evolution 不打开 protected case 文件 | Path.open spy 在 evaluation/sealed 路径立即失败，且确认 cold/dev case 文件也未打开 |
| 不解码 sealed 标签/观察 | json.loads spy 拒绝 sealed-sentinel/sealed-branch；哨兵本身是非法 JSON，任何错误解码都会失败 |
| 不解码同 split 未请求根 | 最终 decoder identity 集严格为 evo-one/branch-evo-one |
| 需要 dev 时显式授予 | evolution+dev 手工用例只加载指定两根，仍不读 sealed |
| 默认 oracle scope 安全 | 默认只载 cold，未打开 streams 或 evaluation |
| 跨 split 请求拒绝 | 只授予 evolution 却请求 dev 根时，在 oracle 文件打开前拒绝 |
| 空/无效授权不读文件 | 空 case_ids 不读任何内容；非法 scope 在文件读取前拒绝 |
| 原回放行为仍可用 | 合法根经授权后只揭示所选分支观察；原授权、反馈门槛和评分边界回归通过 |

```bash
uv run python -m pytest tests/content/test_replay_split_isolation.py -q
# 8 passed in 0.02s
uv run python -m pytest tests/content/test_replay_split_isolation.py \
  tests/content/test_content_pipeline.py \
  -k 'split_isolation or evaluator_is_opt_in or feedback_is_gated or report_scoring_rejects' -q
# 11 passed, 6 deselected in 0.65s
```

第二条命令只执行明确选择的已有 cold 授权回归，未执行全内容验证或真实 sealed 解码测试。API 负责人另记录其手工集成验证。

## 原实验与后置版本

独立预登记 pilot 使用其自行按根过滤的环境，通过 `EvaluatorReplay.__new__` 复用行为方法，未调用上述 eager 构造器，因此这项通用 API 缺陷不影响原 pilot 的封存读取时间或已存结果。没有新 LLM 调用，没有读取新的真实 sealed 输入，没有重新生成内容包/manifest，没有重新评分原 sealed，没有向 optimizer 回灌任何封存结果。

修改 replay.py 是生产软件后置版本，导致它的 hash 与原 pilot protocol 不同，这是冻结保护预期结果。原 protocol、cost ledger、results、summary、封存质量、blind review pending 和审计记录原样保留；复核旧运行应使用其已记录冻结 Git/source 版本，不能以当前源码改写旧成绩。
