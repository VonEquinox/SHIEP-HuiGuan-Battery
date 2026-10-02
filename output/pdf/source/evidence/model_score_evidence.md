# PDF 模型与分数证据（2026-10-02）

基线 main 固定为 `c4203014c4c6999c2d176b1402d596813a072f73`；当前 DEV 为 `0d9a53de2afaf062e4a2fa433dec97f759d56680`。本文件只读取已归档报告、JSON模型指标和协议，不训练、不重新打开 final、不读取 protected/sealed 原始数值。

## 1. main 到 DEV 的能力差异

main 的数值主线是 XJTU-only 的 71D 部分恒流曲线（3.7–4.1V preceding CC prefix）+初始参考测量，冻结 TabICL+ExtraTrees 等权混合，3 seed、每seed8个 TabICL estimators。开发 OOF 集为21电芯/2058窗口，MAE0.585897pp。三个受保护的 *-5 电芯没有评分。出处：`c4203014c4c6999c2d176b1402d596813a072f73:model_lab/reports/round3/champion_hybrid_v2_streaming/manifest.json`，字段 `development_ensemble_mae_pp`。

DEV 增加统一30D统计+显式缺失位、来源/化学体系/协议支持边界、多来源 M1 与 M2、当前 H-M1量化优化、新schema第六通道temperature_valid。来源从XJTU/NCM扩展到MATR/LFP；这是可服务来源增加的证据。不能把0.585897与0.384127直接相除宣称main→DEV误差降低，因为特征、窗口、标签语义/校准和人群不同。

## 2. 数据扩容：独立电芯和窗口均给出

| 口径 | 原XJTU电芯/行 | 联合电芯/行 | 总量倍数 | 新增比例 |
|---|---|---|---|---|
| 完整comparison | 21/168 | 56/448 | 2.6667× | 166.67% |
| 可反复开发non-final | 18/144 | 47/376 | 2.6111× | 161.11% |
| 真正用于train | 11/88 | 28/224 | 2.5455× | 154.55% |

公式：总量倍数=联合/原XJTU；新增比例=(联合−原XJTU)/原XJTU×100%。扩容数据来自 `battery_platform/research/joint_xjtu_matr/summary/joint_benchmark_summary_20261002.json` 的 `data_scale`，分割协议 `battery_platform/docs/JOINT_XJTU_MATR_RESULTS_20261002.md`。以上不是全部下载规模；不把 cycle 数当作独立电芯。完整comparison56电芯中含9final；当前新schema重训只用47non-final。

| split | XJTU电芯/行 | MATR电芯/行 | 联合电芯/行 |
|---|---|---|---|
| train | 11/88 | 17/136 | 28/224 |
| dev | 3/24 | 6/48 | 9/72 |
| calibration | 4/32 | 6/48 | 10/80 |
| 历史comparison final | 3/24 | 6/48 | 9/72 |

## 3. 当前 H-M1：模型做什么、为什么这样改

旧M1按source::chemistry::protocol切分域头，XJTU协议的训练样本被拆小。H-M1在每个source内部汇集各protocol的train行，分别拟合q05/q50/q95 GBDT共享主干（160棵/深3/叶5/学习率0.03），再对各quantile加source-level残差GBDT（80棵/深2/叶5/学习率0.03/残差权重1.0）。XJTU与MATR保留各自归一化与头，不是跨来源共用所有权重。输入仍为30D，target为source内标准化log(SOH)，统计量只从train拟合。电芯等权，避免窗口多的电芯占据优势。q05/q50/q95逐行排序后中间值为点预测。设计目的是让XJTU协议共享来源内统计规律，同时保留MATR稳定性与量化输出。

冻结结构先经过128配置×3seed层级搜索和点预测宽搜索；最终选择只基于dev，两域门控：MATR≤旧M1+0.10pp；XJTU严格低于旧M1和同包MLP，过门后按XJTU_MAE+0.2×MATR_MAE排序。calibration用于稳定性报告；没有使用final标签选择。模型JSON重新推理各seed最大SOH差0。当前状态是H-M1研究量化原型，尚未接入完整DomainBaseline的efficiency/survival/fault生产契约。出处：`battery_platform/docs/HM1_OPTIMIZATION_RESULTS_20261002.md`、`battery_platform/research/f01_channel_validity_20261002_qualified/hm1_quantile_development.json`。

## 4. 同人群 development 分数对比

统一口径：单位SOHpp，越低越好；每电芯先求MAE，再在来源内电芯等权宏平均；3seed(0/1/2)均值±样本标准差。dev为XJTU3电芯/24行、MATR6电芯/48行；train28电芯/224行。当前H-M1/M1/M2为新schema独立重训权重；MLP/LSTM/LightGBM为修复前同population标量历史对照：30D原始输入、标签和它们自身预处理配方没有变化，未把旧模型载入新schema伪称新评估。

| 方法 | XJTU dev MAE(pp) | MATR dev MAE(pp) | 版本状态 |
|---|---|---|---|
| H-M1 | 0.3841 ± 0.0173 | 1.5290 ± 0.0344 | 新schema重训 |
| M1 | 0.6095 ± 0.0659 | 1.7021 ± 0.0082 | 新schema重训 |
| MLP | 0.7297 ± 0.1587 | 5.3303 ± 3.2562 | 历史scalar对照 |
| LSTM | 4.4909 ± 0.0058 | 12.0570 ± 0.2728 | 历史scalar对照 |
| LIGHTGBM | 1.2669 ± 0.0000 | 4.0649 ± 0.0000 | 历史scalar对照 |
| M2 | 4.8088 ± 4.1059 | 8.5294 ± 0.6477 | 新schema重训 |

每个数的出处：H-M1/M1/M2 → `battery_platform/research/f01_channel_validity_20261002_qualified/development_model_comparison.json` 的 `models.<method>.new6channel`；MLP/LSTM/LightGBM → `battery_platform/research/joint_xjtu_matr/baselines/development/v2_30d_domain_20261002.json` 的 `rows(method,part=dev,seed)`，按seed均值和statistics.stdev重算。LightGBM三个seed相同是确定性配置，不代表没有泛化不确定性。LSTM以30个统计字段作30步单通道序列，不冒称MATR真实波形时序。

| H-M1 对照 | XJTU绝对降低(pp) | XJTU相对下降 | MATR绝对降低(pp) | MATR相对下降 |
|---|---|---|---|---|
| M1 | 0.2254 | 36.98% | 0.1732 | 10.18% |
| MLP | 0.3456 | 47.36% | 3.8013 | 71.32% |
| LSTM | 4.1068 | 91.45% | 10.5281 | 87.32% |
| LIGHTGBM | 0.8828 | 69.68% | 2.5360 | 62.39% |

公式：(baseline MAE−H-M1 MAE)/baseline MAE×100%。baseline为分母。这里是本项目具体实现的开发比较，不是充分调优全部架构后的公开领域SOTA结论。

## 5. 量化区间：覆盖与宽度都必须呈现

| split/source | MAE(pp) | RMSE(pp) | 实测90%区间coverage | 平均宽度(pp) |
|---|---|---|---|---|
| dev/xjtu | 0.3841 ± 0.0173 | 0.4810 ± 0.0263 | 95.83% | 8.9372 ± 0.1595 |
| dev/matr | 1.5290 ± 0.0344 | 3.9254 ± 0.0539 | 81.25% | 12.8174 ± 0.1375 |
| calibration/xjtu | 0.6944 ± 0.0427 | 0.9831 ± 0.0157 | 72.92% | 9.6395 ± 0.2088 |
| calibration/matr | 0.1751 ± 0.0264 | 0.3285 ± 0.0598 | 93.06% | 16.9896 ± 0.3415 |

出处：`battery_platform/research/f01_channel_validity_20261002_qualified/hm1_quantile_development.json` 的 `results[seed].metrics[split][source]`。dev的XJTU coverage95.83%、MATR81.25%表明未统一达到名义90%校准。宽度分别约8.94pp/12.82pp，不能只展示低MAE而称安全风险已校准。calibration为XJTU4电芯/32行和MATR6电芯/48行，不与dev混算。

## 6. 历史 final 对照：与当前 development 分开展示

| 方法 | XJTU MAE(pp) | MATR MAE(pp) |
|---|---|---|
| M1_joint | 1.1768 ± 0.1121 | 2.4528 ± 0.0074 |
| M2_joint | 3.0159 ± 0.6034 | 9.3918 ± 1.7472 |
| MLP_JOINT | 0.6338 ± 0.0598 | 4.5717 ± 2.9026 |
| LSTM_JOINT | 4.1695 ± 0.7871 | 10.3116 ± 2.1715 |
| LIGHTGBM_JOINT | 1.5716 ± 0.0000 | 3.8754 ± 0.0000 |

出处：`battery_platform/research/joint_xjtu_matr/summary/joint_benchmark_summary_20261002.json` 的 `models`。XJTU3电芯/24行是历史暴露comparison final；MATR6电芯/48行在配方冻结后一次评分；均为pre-F01历史结果。没有新H-M1 final，不能把H-M1的dev数值放进此表。

| 历史联合M1对照 | XJTU相对误差下降 | MATR相对误差下降 |
|---|---|---|
| MLP_JOINT | -85.67% | 46.35% |
| LIGHTGBM_JOINT | 25.12% | 36.71% |
| LSTM_JOINT | 71.78% | 76.21% |
| M2_joint | 60.98% | 73.88% |

负值表示M1更差：历史XJTU上MLP优于M1；MATR上M1优于这些基线。旧文档某段把LightGBM相对M1的方向写反，PDF务必按JSON数据与上述公式：XJTU M1比LightGBM低25.12%（1.17675 vs1.57159），不是LightGBM比M1好。

## 7. 加入MATR后的可迁移性：同方法OOD对照

| 方法 | XJTU-only→MATR MAE(pp) | source-aware联合→MATR MAE(pp) | 相对下降 |
|---|---|---|---|
| mlp | 23.6047 | 4.5717 | 80.63% |
| lstm | 10.7994 | 10.3116 | 4.52% |
| lightgbm | 9.8597 | 3.8754 | 60.69% |

出处：`battery_platform/research/joint_xjtu_matr/summary/joint_benchmark_summary_20261002.json` 的 `xjtu_only_transfer_by_method` 与 `models`。3seed，相同MATR final6电芯/48行；XJTU-only只用XJTU train/dev，MATR标签不选型。这是数据来源加入后的性能变化，不是main模型的跨域评分。XJTU-only M1无MATR合法domain head，只能unsupported，不造loss。

## 8. F01新schema后的变化、版本界限

| 方法 | 旧XJTU dev MAE | 新XJTU dev MAE | 旧MATR dev MAE | 新MATR dev MAE |
|---|---|---|---|---|
| H-M1 | 0.3841 | 0.3841 | 1.5290 | 1.5290 |
| M1 | 0.6095 | 0.6095 | 1.7021 | 1.7021 |
| M2 | 2.6719 | 4.8088 | 9.7474 | 8.5294 |

独立重建376开发行、9次重训，不复用旧权重或重写旧指标。扫描4744有基础数组分段/5965256基础有效点，准入源内未触发旧缺温缺陷；MATRsummary和DYAD无物理曲线单独标不适用。M2结构输入通道、标准化和初始化一起变化：XJTU退化、MATR改善，不是温度缺失单因素因果证明；M2未选用。出处：`battery_platform/docs/F01_CHANNEL_VALIDITY_RETRAIN_20261002.md`。

XGBoost未运行；没有把LightGBM称为XGBoost。当前研究候选为新schema H-M1；完整生产多头包尚未切换H-M1。旧M1是原跨来源部署候选。全部对比区分schema、人群和split，未打开protected *-5。
