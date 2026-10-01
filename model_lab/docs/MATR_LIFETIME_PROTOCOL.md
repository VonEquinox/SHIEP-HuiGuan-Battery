# MATR 物理循环寿命前缀协议

此文档记录新增的独立特征构造器及输入/标签验证范围。构造器测试不代表寿命模型验证；后续真实开发训练/删失指标已单独记录在 `reports/v2/matr_lifetime_development_masked_20261002/BENCHMARK.md`，仍不构成部署指标或最终测试。现有容量图的序号特征、原 V1 数据和结果均不由此协议改写。

## 输入资格与来源

入口为已经完成来源解析与身份核验的 V2 `identity_map.parquet`、`cycles.parquet`、`segments.parquet`、`targets.parquet` 和冻结 `split_manifest.json`。构造器不读取原始 MATLAB 文件，也不能用文件存在、下载完成、批次通道位置或元数据替代原始 barcode 核验。

身份必须为 MATR 实验数据、barcode 对应的 `physical_cell_id`，并有明确身份依据。实际 corrected MATLAB 文件采用 `identity_basis=original_corrected_mat_barcode`，还必须有 `identity_verified=true`；该字段必须来自上游实际 barcode 解码和延续关系核验。原始 Arbin barcode 与已核验原始身份也可准入。仅批次加通道的位置身份不准入。循环表的 `physical_cycles_known` 必须逐行明确为布尔真；图表序号不能改名成为物理循环。

读取顺序为身份表、冻结 split、准入 ID，再以 Parquet ID 过滤与列投影读取数值。默认只准入 `train`、`dev`、`calibration`，`final`、`final-test`、`sealed`、`protected` 及其他 split 在数值读取之前排除。源数值表的已记录 SHA-256 从源 manifest 传递，不对含封存对象的数值表重新全表计算哈希。身份、split 与源 manifest 的 SHA-256 单独记录；输出 NPZ 的哈希在写入后计算。

此处“读取前排除”指向 Parquet reader 提交准入 ID 过滤条件，排除对象的数值行不会返回特征构造器或参与训练。若物理文件把不同对象放在同一 row group，底层 reader 的内部扫描/解码由存储格式决定；该接口不宣称底层字节从未被读取。要求物理存储级隔离的封存数据应由上游分文件或分区保存。

不同来源版本可能包含相同 barcode；corrected MATLAB 的 B3 批次与此前容量图对象存在身份重叠。`--exclude-identity-manifest` 可传入先前特征或 split 的 JSON 身份元数据，提取所有此前 `final` MATR barcode，在本次数值列投影前排除，并记录 `previously_consumed_final_identity`、元数据 SHA-256、去重后的规范化 barcode 清单与计数。barcode 用命名空间与大小写规范化匹配，适配原官方大小写与新规范身份；不会打开该元数据引用的 NPZ。原新来源 split 的 assignment 保留，排除不等于把对象移动到其他 split。

即便历史 final 已排除，历史 train/dev/calibration 对象仍可能重叠，应在实际实验记录中披露。因此这次完整轨迹开发实验不构成与此前容量图实验的干净独立泛化比较。

原 `source_protocol_id` 优先成为精确 `protocol_id` 域键；不同充电 policy 保留不同 `matr::chemistry::protocol_id` 域。构造器不会为了增加样本量而合并 policy。若循环中的 policy 与身份 policy 冲突，该对象排除。同一 policy 域若混合不同寿命阈值定义，构造器失败，不静默选择一种。

## 固定查询与可见输入

默认查询为物理循环 50、100、200，可通过显式的严格递增整数列表配置。配置必须在模型训练前冻结，不能根据未来寿命或结果选择查询。所有输入的物理循环、观测时刻和可用时刻均必须早于查询；整数循环的 `visible_cutoff=query-1`。

SOH 参考容量为物理循环 10 或之后的首个有效正容量，按对象冻结。参考容量及其可用时刻必须在查询之前，否则该查询排除。查询时刻若有精确实测容量，`y_soh=Q(query)/Q(reference)`；没有精确实测值时 SOH 使用 NaN 缺失标签，不对未来容量插值或假造 SOH。

容量历史及真实曲线历史均最多 32 条，每条曲线最多 256 点。曲线由实际电压、电流、温度及时间字段构造；不存在的曲线为全零且 `sequence_mask=0`。统计向量复用 F30（15 个统计量及各自缺失标志），容量历史只用可见记录。`cycle_life`、事件终点、死亡循环、最终容量、隐藏标签等字段不在数值投影允许列中，也不进入输入向量。事件定义、未来标签时刻仅作为训练标签与来源元数据保存。

预处理参数仍应仅由训练对象拟合。本构造器不拟合预处理、模型或校准参数。

## 剩余物理循环与删失

上游 RUL 标签必须明确 `unit=cycle`、源 `target_definition_id`、阈值 Ah、比较符和删失边界。本构造器把绝对物理循环边界减去查询循环，得到剩余物理循环标签，保持以下约定。

| 原标签 | 输出 kind | 输出下界 | 输出上界 |
| --- | --- | --- | --- |
| 精确事件 T，且 T 大于查询 q | 1 | T-q | T-q |
| 右删失至 C，且 C 不早于 q | 0 | C-q | 0（未观测事件上界） |
| 区间事件 L < T ≤ U，且 L 不早于 q | 2 | L-q | U-q |

精确事件或区间上界不大于查询时刻，意味着事件已发生，该查询排除。区间下界早于查询且上界晚于查询时，无法确定对象在查询时仍存活，该查询排除。右删失早于查询同样不能证明查询时存活，该查询排除。若查询恰等于区间下界，该对象在下界尚未发生事件，零下界保留。右删失恰在查询的零观察期可以保留，其寿命似然本身不提供超出查询的事件信息。

源阈值比较符逐字保留。MATR corrected MATLAB 的 0.88 Ah **严格小于**定义与“小于等于 0.88 Ah”是不同目标；输出定义 ID 显式包含来源定义、阈值和比较符。二者不得互换，最后观察循环加一也不得作为假定事件。

标签数组沿用 `battery_features_v2`：`y_soh`、缺失 `y_efficiency`、缺失 `y_fault=-1`、`survival_kind/lower/upper`。效率没有同 SOC 与计量边界的完整证据，故保持缺失；源数据没有已确认故障标签，故故障保持缺失。剩余寿命与未来阈值风险必须由同一个删失感知生存模型得到。

## 使用与留痕

```bash
uv run python -m model_lab.scripts.v2.lifetime_features \
  --derived model_lab/data/derived/v2/qualified_matr_run \
  --out model_lab/data/derived/v2/matr_lifetime_prefix_run \
  --query-prefixes 50 100 200 --history 32 --points 256 \
  --exclude-identity-manifest model_lab/data/derived/v2/prior_features/features.json
```

输出目录必须完全不存在，已存在目录不会覆盖。`--help` 只显示接口；`--dry-run` 验证路径和参数后输出计划，不打开来源表。实际 manifest 保存每个查询的身份、精确域、参考容量、可见边界、标签定义和证据引用，并保存排除原因及三类删失计数。冻结 split 的内容与身份归属不改写。

新增文件为 `modeling/v2/lifetime_features.py`、`scripts/v2/lifetime_features.py`、`tests/v2/test_lifetime_features_v2.py` 和本协议。五个小型 fixture 测试覆盖精确/右删失/区间的剩余循环、存活边界与严格阈值、序号拒绝、未来输入不变性、数值读取前本次与历史 final/封存对象排除与 policy 隔离。实际 qualified derived run、训练、校准与开发集结果由独立实验记录登记；本协议不填入未经执行的指标。

本次构造器验证命令为 `.venv/bin/python -m pytest model_lab/tests/v2/test_lifetime_features_v2.py -q`，结果为五项通过。CLI 的 `--help` 与含历史 final 排除参数的 `--dry-run` 已执行并正常退出，dry run 返回 `source_tables_opened=false`。此阶段未读取实际数值来源、未运行训练、未读取 final，也未修改 Git 提交；后续实际实验由主协作 Agent 按阶段登记和提交。

## 后续真实开发执行（Phase 17）

完整 corrected MAT 来源随后通过实际条码/续测核验。保持本协议输入边界，先排除六个旧 final，再建立实际123对象368窗口的开发特征，79/23/21/0。首次 fit 之前因计算预算新建8历史×64点版本，50/100/200 query 与精确 policy 不变。最初32×256包未训练。

真实 M1/M2 三种子和 M2 三组消融已执行；首次离线未知policy遮罩问题保留诊断记录，纠正版使用完全相同配置重新冻结/运行，未消费 final。结果、身份人口分母、29个旧非final对象暴露历史、右删失条件、逐域支持/CQR不足、重载包和真实命令见独立 `BENCHMARK.md` 与 `V2_IMPLEMENTATION.md`。这段后续记录与上文构造器阶段的五个fixture测试明确区分。
