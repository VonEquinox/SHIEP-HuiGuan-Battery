# F01：温度有效性、实际触发盘点与独立特征版本重训

日期：2026-10-02。对应修复：`model_lab/modeling/v2/features.py`、特征契约、M2 输入通道和模型运行时 schema 配对检查。当前研究产物目录：`battery_platform/research/f01_channel_validity_20261002_qualified/`。

## 结论与适用范围

缺温与真实 0°C 在旧 `segment_view` 中不能区分的最小复现成立。修复增加第六通道 `temperature_valid`，温度只在连续有限值范围内插值；无观测的位置使用零填补，同时有效性为 0。统计温度只使用有效点；部分缺失与全部缺失均保留缺失标记。标准化只使用合格温度，标准化后仍把缺温位置置为中性填充值，并保留二元有效性。

这次对**允许进入 development 的来源表**进行实际盘点，合计检查 4,744 条有 V/I/time 数组的来源分段记录，未发现旧缺温置零触发。这个分母包含多个适配来源，可能存在跨来源重叠电芯或分段；它不是 4,744 条独立物理电芯证据。未读取旧 final 与保护电芯数值，因此不把结论推广为“全部数据没有缺温”，也不能将 F01 认定为历史负迁移的原因。

重新生成了独立 schema 与权重版本，H-M1、M1、M2 各 3 个随机种子全部完成 development 重训。H-M1 与 M1 的 development MAE 保持不变；M2 的 XJTU MAE 变差而 MATR MAE 变好。M2 不替代已选 H-M1，也不把这个变化解释为 F01 导致或解决了负迁移。

## 数值读取前的排除规则

先读取 identity 与 split 元数据，再用 Parquet `physical_cell_id` filter 返回数值行：

- 仅接收原冻结 `train`、`dev`、`calibration`，不重分割电芯；
- 排除 XJTU `*-5`，不读取其曲线、目标或预测；
- 排除 XJTU 历史 final 的 3 个物理身份；
- 排除 MATR official summary 历史 final 的 6 个 barcode，即使 corrected source 的新 split 将同一身份列入 development；
- 保留“因非 development split 排除”与“历史 final 身份排除”的完整清单；
- 不对原组合数值表重新计算哈希。Arrow 可能内部扫描共享 row group，但排除行不会返回到 Python、进入特征构造或训练。

Parquet schema/footer 与 JSON identity/split 元数据读取不等于 final 数值评价。盘点只计算返回的已准入数值行。

## 实际盘点

“合格曲线”在此指至少两点 V/I/time 数组；温度覆盖还要求这些基础数组点有限。这是缺失通道盘点，不代替化学体系、单位、传感器粒度等源资格审核。

| 来源适配表 | 准入对象 | 返回分段 | 有 V/I/time 数组分段 | 缺数组 / 短数组 / 全非有限 / 局部非有限 | 旧缺温置零触发 |
|---|---:|---:|---:|---|---:|
| XJTU `xjtu_final_20261002` 的 development 身份 | 18 | 581 | 581 | 0 / 0 / 0 / 0 | 0 / 581 |
| MATR official summary 的 development 身份 | 30 | 3,225 | 0 | 不适用，整个曲线不存在 | 不适用 |
| MATR corrected，排除历史 final barcode | 129 | 4,049 | 4,049 | 0 / 0 / 0 / 0 | 0 / 4,049 |
| MATR Arbin 开发电芯 | 1 | 32 | 32 | 0 / 0 / 0 / 0 | 0 / 32 |
| CH-BatteryGen 输入适配表（非本次 SOH 训练来源） | 82 | 82 | 82 | 0 / 0 / 0 / 0 | 0 / 82 |
| DYAD 输入适配表（统计特征，无物理曲线） | 85 | 680 | 0 | 不适用，整个曲线不存在 | 不适用 |

在上述有数组分段中，基础有效点总计 5,965,256 个，温度有效点也是 5,965,256 个；缺温点、真实全零温度分段、真实 0°C 点均为 0。CH/DYAD 只参加输入盘点，未加入本次 XJTU+MATR SOH 重训。CH 数组的有限性不证明它们属于与 XJTU 一致的真实单电芯温度测量。

MATR summary 的 V/I/time/temperature 均为空。旧 `segment_view` 在 `n<2` 时已经返回全零 sequence 与全零 point mask，统计缺失标记为 1。因此这类输入原本属于“没有曲线”，不属于“有效 V/I/time 曲线里的缺温被当成实测 0°C”。

完整按来源计数、比例、有效点分母与排除清单：`source_temperature_inventory.json`。旧特征元数据影响清单：`historical_feature_impact_inventory.json`，该清单没有打开相应旧 NPZ 数值数组。

## 新特征版本与冻结人口

| 项目 | 旧版本 | 新版本 |
|---|---|---|
| schema | `battery_features_v2` | `battery_features_v2_channel_validity_1` |
| prefix data version | `v2-prefix-1` | `v2-prefix-channel-validity-2` |
| combined data version | `v2-multisource-adapters-1` | `v2-multisource-adapters-channel-validity-2` |
| sequence | 5 通道 | 6 通道，第六维 `temperature_valid` |
| scalar statistics | 15 值 + 15 missing flags | 15 值 + 15 missing flags；温度值只用合格点 |
| 温度统计适用 domain | 无显式声明 | `temperature_stat_domains=[0,1,2,3]`，组合器重新映射 |
| 模型配对 | 旧 schema 与旧权重 | 新 schema 与独立重训权重；运行时拒绝错配 |

本次新 combined bundle 为 376 行，其中 XJTU 144、MATR 232；train 224、dev 72、calibration 80。它沿用旧 development 人口：train 28 个独立电芯，dev 9 个，calibration 10 个。MATR summary 中一个准入身份没有构成有效前缀/目标对，所以进入组合模型的 MATR 对象是 29 个，而不是来源盘点的 30 个。

以 `(source_id, physical_cell_id, split, query_time)` 对齐旧 development bundle 后：30D 原始 scalar 特征 376 行全部逐位一致，最大绝对差 0；SOH 标签最大绝对差 0；没有改变任何冻结 split。sequence 新增有效性通道；温度标准化契约独立版本化。

`feature_input_diff.json` 保存对齐验证；`feature_rebuild_receipt.json` 保存新 bundle schema、行数与哈希。初次本地构造发生在温度统计 domain discriminator 尚未冻结时，该尝试未训练、未产生模型指标、未提交，已经清理；最终使用 `_qualified` 版本。

## 重训方法与结果

冻结原训练配方，不开启新搜索、不读取 final 反馈：

- H-M1：source-level q05/q50/q95 GBDT 160 棵、深度 3、叶节点 5，残差 GBDT 80 棵、深度 2、叶节点 5；两阶段学习率 0.03，cell-balanced，source-normalized log-SOH。它是只消费 30D scalar 的研究原型，保留独立 train-only median/mean/scale 配方 `f01-scalar-train-median-mean-scale-v1`，明确不消费 sequence；每个新 seed JSON 绑定新 schema、data version、bundle/arrays SHA、特征构造代码 SHA 和 `n_features=30`。
- M1：原 domain quantile GBDT，80 棵、3 seeds、无 NGBoost；通过新 `fit_preprocessor` 的温度适用 domain 规则重训，旧权重完全没有复用。
- M2：原 12 epochs、batch 8、learning rate 0.001、fixed-domain-object loss 与相同任务权重；输入卷积 `channels=6`，使用新温度有效性与标准化规则，每个 seed 重新初始化并训练。

指标均为 development，单位 SOH percentage points。先对每个电芯的前缀行求 MAE，再在 source 内对电芯平均；表格展示三个 seed 的均值 ± sample standard deviation。

| 方法 | schema/权重版本 | XJTU dev MAE | MATR dev MAE |
|---|---|---:|---:|
| H-M1 | 旧 5 通道 bundle 配方，历史开发结果 | 0.3841 ± 0.0173 | 1.5290 ± 0.0344 |
| H-M1 | 新 6 通道 bundle，独立新 scalar 权重 | 0.3841 ± 0.0173 | 1.5290 ± 0.0344 |
| M1 | 旧 schema/transform，历史开发结果 | 0.6095 ± 0.0659 | 1.7021 ± 0.0082 |
| M1 | 新 schema/transform，独立新权重 | 0.6095 ± 0.0659 | 1.7021 ± 0.0082 |
| M2 | 旧 5 通道/transform，历史开发结果 | 2.6719 ± 1.4276 | 9.7474 ± 1.0501 |
| M2 | 新 6 通道/transform，独立新权重 | 4.8088 ± 4.1059 | 8.5294 ± 0.6477 |

H-M1 的三个新 seed JSON 重放误差均为 0。M1 与 H-M1 数值不变符合本次真实来源输入没有触发 F01、scalar 特征逐位一致的事实。M2 的第六输入维度改变了卷积参数形状和初始化，同时更新了缺失温度的标准化；这不是单变量因果实验，不能将它的两域变化归因于缺温修复。新 M2 仍明显弱于 H-M1，未选用、未部署。

本次未重新训练 MLP：已验证原始 scalar 30D 输入、标签、冻结人口完全一致，MLP 自身的 train-only 预处理配方也没有改动。旧联合 MLP development 指标只作为历史 scalar 对照（XJTU 0.7297、MATR 5.3303 pp），不把旧模型加载到新 schema 后伪称为新评估。如未来 scalar 输入变动，重训脚本会明确停止比较并要求新的同 bundle MLP。

`development_model_comparison.json` 包含完整每 seed 指标、均值、sample SD 和解释。每个 M1/M2 新 run 均保存 config、schema、preprocessor、权重 SHA 与 `final_accessed=false`；H-M1 新 receipt 不保留历史 final MLP 分数。

## 历史保留与使用边界

对当前旧 development bundle、旧 H-M1 3 seed 权重/receipt、旧 M1/M2 3 seed 权重/run/dev metrics 记录修复前后 SHA，全部一致：`historical_artifact_hashes_before.json` 与 `historical_artifact_hashes_after.json`。这份校验只打开旧 development 数值数组/模型，不读取历史 final 数值数组。旧 final 结果没有覆盖或重新评分；protected 电芯继续封存。

旧 prefix/lifetime/fault/multisource artifacts 作为历史研究保持旧 schema，不自动升级现有权重。新的 prefix、lifetime、fault builders 输出明确新 schema；mixed schema 组合被拒绝。当前选用候选是新 schema 绑定的 H-M1 研究原型；这次没有把它宣布为新的 untouched-final SOTA，也没有把研究 JSON 直接代替完整应用多头部署包。

## 复现

代码与最终产物均在本提交中保留。构造与重训输出目录不可覆盖；在干净 checkout/另一新版本目录运行：

```sh
uv sync --locked
uv run python -m battery_platform.research.repair_f01_features --rebuild --output-dir battery_platform/research/f01_reproduction_local
uv run python -m battery_platform.research.retrain_f01_development --output-dir battery_platform/research/f01_reproduction_local
```

已经存在的目录会拒绝覆盖，不能直接在当前已归档目录重复运行并改写指标。模型计算顺序为 H-M1 的 3 seed → M1 的 3 seed → M2 的 3 seed，任意时刻仅一个模型训练进程。源表未公开提交时须先按原数据规范准备本地 qualified parquet；本次另存的准入表与其 split metadata 供核对本次人口及输入。
