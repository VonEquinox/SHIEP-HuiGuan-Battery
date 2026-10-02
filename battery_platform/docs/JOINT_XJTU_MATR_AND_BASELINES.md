# XJTU + MATR 联合训练与基线对照记录

本文件记录本阶段新增的实验目标、数据口径、分割规则、训练方法、图表和每次运行结果。它只记录本阶段新实验，不改写 `model_lab/` 中已经冻结的历史结果。

## 目标

本阶段只做两条电池数据线：

1. XJTU-only：只使用 XJTU 的训练电芯。
2. XJTU+MATR：使用 XJTU 与 MATR 的训练电芯联合训练。

两条线使用相同的 SOH 评估定义、随机种子和特征协议，并分别在 XJTU 与 MATR 的独立评估电芯上报告 MAE、RMSE 和逐电芯结果。MATR-only 暂不作为本阶段主实验。

同时增加 MLP、LSTM、LightGBM 基线，要求它们使用同一训练/评估分割。现有 V2 M1 是 source/domain 分头的概率 GBDT；它会作为安全基线保留，但不能把它的 domain-specific 结果解释成跨来源迁移提升。

## 数据和规模口径

当前可比的是 V2 prefix-SOH 特征包：

| 数据 | 可建模电芯 | SOH 窗口 | train/dev/calibration/final 电芯 |
|---|---:|---:|---|
| XJTU feature population | 21 | 168 | 11 / 3 / 4 / 3 |
| MATR official summary | 35 | 280 | 17 / 6 / 6 / 6 |
| XJTU+MATR full comparison package | 56 | 448 | 28 / 9 / 10 / 9 |

完整比较包按可建模独立电芯或 SOH 窗口计，是 XJTU-only 的 `56 / 21 = 2.667x`，新增 35 个 MATR 电芯，增加 166.7%。训练电芯从 11 个增加到 28 个，训练窗口从 88 个增加到 224 个，训练规模为 `2.545x`。用于反复选型的 development/feedback 包会排除所有 final 行，实际为 XJTU 18 个对象/144 行 + MATR 29 个对象/232 行 = 47 个对象/376 行；相对 XJTU development 包的扩大倍数为 `2.611x`。MATR 的 cycle、segment 和历史曲线数量另行记录，不能直接称为独立样本倍数。

MATR 的特征包只有容量历史/统计信息，XJTU 还包含可见曲线序列。两者通过 source-specific adapter 和 mask 进入共同模型；未经说明时，不把两类原始曲线当成同分布。

## 分割和测试规则

- 训练只读 `split=train`。
- 反复比较候选模型、特征和超参数只使用 `dev` 与 `calibration`。
- `final` 只在配方、代码和随机种子冻结后运行一次，用于最终报告。
- XJTU 的 `*-5` protected 电芯继续封存，任何模型选择都不读取其标签。
- 旧的 `xjtu_features_final` 中 3 个 final 电芯属于历史 V1 development population；如本阶段打开，只能标为“历史暴露的 V2 comparison final”，不能当作全新独立泛化测试。
- 如果一个集合被反复查看并用于调参，它的名称必须是 `feedback/dev`，不能继续称为 untouched testing set。

## 主要比较

每个模型都记录：

- XJTU dev/final 的 MAE、RMSE、逐电芯误差；
- MATR dev/final 的 MAE、RMSE、逐电芯误差；
- 三个随机种子的均值和样本标准差；
- 相对 XJTU-only 的 `ΔMAE = joint - xjtu_only`；
- 误差下降比例 `(xjtu_only - joint) / xjtu_only`；
- 训练电芯数量、SOH 窗口数量、特征和代码哈希。

目标是检验联合训练是否同时满足：XJTU 指标不恶化，MATR 指标改善。这个目标不能预先保证；如果 M2、MLP、LSTM 或 LightGBM 出现负迁移，原始结果也必须保留。

## 模型状态

| 方法 | 输入 | 训练方式 | 状态 |
|---|---|---|---|
| V2 M1 quantile GBDT | 30D统计特征 | source/domain 分头 | 已完成；联合 MATR final MAE `2.4528±0.0074 pp` |
| V2 M2 multitask | 统计特征+历史序列 | 共享编码器+域适配器 | 已完成；联合 MATR final MAE `9.3918±1.7472 pp`，保留负迁移 |
| MLP | 30D统计特征 | source-aware 输入 | 已完成；联合 MATR final MAE `4.5717±2.9026 pp` |
| LSTM | 历史序列+mask | source-aware 输入 | 已完成；联合 MATR final MAE `10.3116±2.1715 pp` |
| LightGBM | 30D统计特征 | source-aware 输入 | 已完成；联合 MATR final MAE `3.8754 pp` |

XGBoost 当前环境没有安装，本阶段不把 LightGBM 的结果冒充 XGBoost。若后续增加 XGBoost，必须使用同一分割和同一报告格式。

## Agent 试验边界

已有 Agent 的 sealed 结果已经冻结：共享基线 0.7000，A2 为 0.8556，A4 为 0.3111。sealed 结果不能再反馈给优化器。后续优化只在新的 evolution/dev/feedback 集合进行，冻结后对新 sealed 集合做一次验收；0.85/0.90 是开发门槛或目标，不能预先写成最终成绩。

## 输出和图表

本阶段最终报告至少包含：

1. 数据规模图：XJTU-only 与 XJTU+MATR 的独立电芯数、SOH 窗口数、训练电芯数。
2. 性能图：每个模型在 XJTU 和 MATR 上的 MAE/RMSE，带三种子误差条。
3. 联合训练变化图：`ΔMAE` 与相对误差下降率，XJTU 与 MATR 分面展示。
4. 覆盖范围图：NCM/XJTU 到 NCM+LFP/MATR 的来源和化学体系覆盖变化。

所有图表从机器可读 JSON/CSV 生成，图中标注 split、独立电芯数和“历史暴露 final / protected sealed”状态。

## 当前限制

- XJTU 与 MATR 的目标虽然都叫 SOH，但参考容量、采样协议和曲线可见性不同。
- M1 的 domain 分头设计不会因为加入 MATR 自动改变 XJTU 分支，因此不能把 M1 的联合结果直接称作迁移学习提升。
- MATR official summary 的 final 只有 6 个电芯；任何 final 均需同时报告逐电芯结果和不确定性。
- 旧 XJTU final 与 M0 历史开发人口存在重叠，不能用于声称 M0 的全新独立泛化。

后续每次训练、评估、图表生成和提交都追加到本文件，并在 `docs/V2_IMPLEMENTATION_LOG.md` 记录对应 commit。

## 已完成结果入口（2026-10-02）

实际运行结果、逐 seed/逐电芯回执、模型结构、失败日志、命令和图表已经归档到 [JOINT_XJTU_MATR_RESULTS_20261002.md](JOINT_XJTU_MATR_RESULTS_20261002.md)。完整比较包为 56 个对象/448 行，开发包为 47 个对象/376 行；XJTU 保护的 `*-5` 电芯仍封存。联合 M1 在 XJTU/MATR 上分别为 `1.1768±0.1121 pp` / `2.4528±0.0074 pp`，但联合 MLP 在历史暴露 XJTU final 上更低（`0.6338±0.0598 pp`），因此结果不能简化为单模型在两个来源都领先。后续 development-only H-M1 结构搜索与量化原型见 [HM1_OPTIMIZATION_RESULTS_20261002.md](HM1_OPTIMIZATION_RESULTS_20261002.md)。

机器可读汇总为 `battery_platform/research/joint_xjtu_matr/summary/joint_benchmark_summary_20261002.json`；图表为 `final_mae_comparison.png`、`dataset_scale_comparison.png` 和 `matr_transfer_comparison.png`。首次 M1 的 `ngboost=true` 导入失败由于环境没有 `ngboost`，失败日志保留，正式结果使用明确记录的 `ngboost=false` 重跑。
