# XJTU + MATR 联合实验完整结果（2026-10-02）

本文是本阶段的结果归档。它把数据构造、训练、基线、最终评估、图表和限制放在同一个位置；协议细节仍见 [JOINT_XJTU_MATR_AND_BASELINES.md](JOINT_XJTU_MATR_AND_BASELINES.md)，机器可读结果见 `battery_platform/research/joint_xjtu_matr/summary/`。

## 先给结论

本阶段真正比较的是 **XJTU-only** 与 **XJTU+MATR 联合训练**。MATR-only 没有作为主线。联合包把可建模独立电芯从 21 个增加到 56 个（`2.667x`），训练电芯从 11 个增加到 28 个（`2.545x`），非 final 的开发/反馈对象从 18 个增加到 47 个（`2.611x`）。按 SOH 窗口，完整包从 168 行增加到 448 行；开发包从 144 行增加到 376 行。

在这套 30D V2 特征和固定分割上，最终用于跨来源部署的候选是 **联合 M1**：它在 MATR final 上的 cell-macro MAE 为 `2.4528 ± 0.0074 pp`，低于联合 MLP 的 `4.5717 pp`、LightGBM 的 `3.8754 pp`、LSTM 的 `10.3116 pp` 和 M2 的 `9.3918 pp`。相对这些方法，M1 在 MATR MAE 上分别低 `46.35%`、`36.71%`、`76.21%` 和 `73.88%`。

XJTU 上没有单一模型全面领先：联合 MLP 为 `0.6338 ± 0.0598 pp`，低于 M1 的 `1.1768 ± 0.1121 pp`；因此 MLP 是这个历史暴露 XJTU final 上的数值冠军。M1 的选择依据是联合部署时的来源覆盖、MATR dev/final 稳定性和可拒判的 source-aware 结构，而不是把 final 标签用于事后挑模型。M1 加入 MATR 后 XJTU 分支完全不变，这是分域头的设计结果；不能包装成 XJTU 迁移提升。M2 在 XJTU 上从 XJTU-only 的 `2.9973 pp` 变成联合的 `3.0159 pp`，轻微恶化 `0.0185 pp`，在 MATR 上也明显负迁移，所以没有选 M2。

## 数据、来源和分割

输入来自仓库已经登记的 XJTU 与官方 MATR 特征包，构造脚本是 [`build_joint_bundles.py`](../research/build_joint_bundles.py)。脚本只读取 `model_lab` 的源包，所有新 bundle、receipt、运行权重和结果都写到 `battery_platform/research/`；没有改写 `model_lab` 历史数据或模型。

| 范围 | XJTU 电芯/行 | MATR 电芯/行 | 联合电芯/行 | 用途 |
|---|---:|---:|---:|---|
| 完整 comparison bundle | 21 / 168 | 35 / 280 | 56 / 448 | 训练、开发、校准和一次性 final 评估 |
| train | 11 / 88 | 17 / 136 | 28 / 224 | 拟合模型；MATR 官方摘要的可用 train 是 17 个 |
| dev | 3 / 24 | 6 / 48 | 9 / 72 | 早停、比较和固定配置 |
| calibration | 4 / 32 | 6 / 48 | 10 / 80 | CQR/校准及开发诊断 |
| final | 3 / 24 | 6 / 48 | 9 / 72 | 配方冻结后每个 seed 只评估一次 |
| 反复选型的 non-final | 18 / 144 | 29 / 232 | 47 / 376 | feedback/dev；不打开 final |

XJTU 的 `final` 三个对象是历史 V1 development population 中已经暴露过的 comparison final，因此本文称为“历史暴露的 V2 comparison final”，不称为全新盲测。XJTU 原来保护的 `Batch-4/R3_battery-5`、`Batch-5/RW_battery-5`、`Batch-6/Sim_satellite_battery-5` 没有被本实验读取。MATR final 只有 6 个电芯，必须结合逐电芯结果和 seed 波动理解。

MATR 特征是容量历史/统计信息，没有与 XJTU 同样的原始曲线；XJTU 具有可见曲线和容量历史。联合包把特征维度整理为共同的 30D统计输入，并保留 `source_id`、chemistry/domain 和曲线可见性边界。MATR 的 cycle/segment 数量不是独立电芯数，不能用来夸大样本倍数。

## 模型到底做了什么

### M1：联合部署候选

M1 是 `DomainBaseline`。它对每个 source/chemistry/protocol domain 独立拟合 SOH 的 q05/q50/q95 quantile gradient-boosting 回归树；q50 是 MAE/RMSE 的点预测，q05/q95 是分布输出。当前实验 `ngboost=false`、每个量化头 80 棵树、三个 seed（0/1/2），只用 train 拟合，dev 用于固定运行配方，calibration 行保留给后续校准。它还保留 efficiency、RUL、fault 头的 support/unsupported 契约；没有合法标签时返回 unsupported，不补造 0。

这套分域结构的直接含义是：XJTU-only 没有 MATR domain head，所以不能把它当成“训练在 XJTU、直接外推到 MATR”的可用 M1；联合 M1 通过 MATR 训练行建立 MATR head。联合训练不会改变 XJTU head 的拟合数据，因此 M1 的 XJTU-only 与联合 XJTU 指标相同是预期行为。本阶段保留了 calibration 行供后续 CQR 校准，但这里汇总的是 q50 的 MAE/RMSE，未把未执行的有限样本 CQR 结果写成已经验证。

首次尝试 `ngboost=true` 时，环境没有安装 `ngboost`，训练在导入阶段失败；失败日志保留在 `runs/xjtu_only_m1/` 与 `runs/xjtu_matr_m1/`。随后明确改成 `ngboost=false` 重跑，结果只使用成功的 no-NGBoost 运行，未把失败运行当作实验分数。

### H-M1 development 优化

在上述历史 comparison final 之后，另开了 development-only 的 H-M1 结构搜索。修正专家学习率为当前 M1 实际值 `0.10` 后，第一轮按域专家加共享主干的 128 个候选中已有配置通过门控，最优约为 XJTU `0.5210 pp`、MATR `1.5610 pp`；随后继续用完整量化输出做第二轮比较。

随后冻结 source-level pooled q05/q50/q95 GBDT 加 source-level residual 的量化研究原型。三 seed 的 development cell-macro q50 MAE 为 XJTU `0.3841 ± 0.0173 pp`、MATR `1.5290 ± 0.0344 pp`，同包 MLP 参考为 `0.7297/5.3303 pp`，旧 M1 参考为 `0.6095/1.7021 pp`。因此它在本轮 development 门控下同时超过 MLP 的 XJTU，并保持 MATR 优于旧 M1。JSON 树包重新推理的最大数值误差为 `0.0`；尚未把它写成新的 final/SOTA 结论，也尚未接入完整 `DomainBaseline` 多任务生产契约。逐步结构、候选表、q05/q50/q95 coverage 和边界见 [HM1 优化结果](HM1_OPTIMIZATION_RESULTS_20261002.md)。

### M2：共享编码器研究候选

M2 是宽度 128 的 masked temporal encoder：30D统计输入与历史序列进入共享表示，按 source 使用 128→32→128 residual adapter，然后分别接 SOH、efficiency、survival、fault heads；缺少的标签由 mask 排除，缺少曲线的 MATR 使用全零序列和显式 mask，不伪造曲线。当前配置为 12 epochs、batch size 8、learning rate `1e-3`、三个 seed。它的目标是让共享表示获得跨来源能力，但本次小样本结果显示负迁移，未选为部署模型。

### MLP、LSTM、LightGBM 基线

三种基线使用同一个联合 final bundle、相同 train/dev/final 划分和三个 seed。归一化统计量只从 train 计算，dev 负责早停，final 标签不参与选择。

- **MLP**：30D标准化特征加 2 位 source one-hot，`128 → 64 → 1`，AdamW，按物理电芯反频率加权；SOH 目标按来源做 log 标准化后回变换。
- **LSTM**：将 30 个统计特征作为 30 步、每步 1 个通道的序列，单层 hidden size 32，再拼接 source one-hot 进入 `34 → 32 → 1` head。由于 MATR 没有真实波形，这个 LSTM 是统计特征序列基线，不应解释为已经使用了 MATR 原始时序曲线。
- **LightGBM**：同样的 30D+source 输入，`n_estimators=800`、`learning_rate=0.03`、`num_leaves=31`、`min_child_samples=12`、`reg_lambda=0.5`，dev early stopping，`n_jobs=1`。环境中没有 XGBoost，因此没有把 LightGBM 结果写成 XGBoost。

另有 XJTU-only OOD transfer 诊断：MLP/LSTM/LightGBM 只用 XJTU train，仍以 XJTU dev 早停，然后在 MATR final 上运行；MATR 标签明确没有用于选择。这一组用于说明“只靠 XJTU 外推 MATR”的代价，不是生产支持路径。

## final 结果

误差单位是 SOH percentage points（ratio 误差乘 100）；表中是三个 seed 的均值 ± 样本标准差，误差按独立电芯先求 MAE/RMSE，再对电芯求宏平均。

| 模型 | XJTU MAE pp | XJTU RMSE pp | MATR MAE pp | MATR RMSE pp |
|---|---:|---:|---:|---:|
| **M1 joint** | **1.1768 ± 0.1121** | **1.6628 ± 0.1801** | **2.4528 ± 0.0074** | **4.7906 ± 0.0174** |
| M2 joint | 3.0159 ± 0.6034 | 3.2873 ± 0.6417 | 9.3918 ± 1.7472 | 19.2911 ± 4.8287 |
| MLP joint, source-aware | **0.6338 ± 0.0598** | **0.8025 ± 0.1333** | 4.5717 ± 2.9026 | 7.0246 ± 4.0104 |
| LSTM joint, source-aware | 4.1695 ± 0.7871 | 5.5207 ± 1.3028 | 10.3116 ± 2.1715 | 17.6366 ± 5.0045 |
| LightGBM joint, source-aware | 1.5716 ± 0.0000 | 2.5781 ± 0.0000 | 3.8754 ± 0.0000 | 8.1823 ± 0.0000 |

LightGBM 的三个 seed 结果完全一致是当前 deterministic 配置的现象，不代表误差为零或不确定性为零。

### XJTU-only 与联合训练

| 模型 | XJTU-only XJTU MAE | 联合 XJTU MAE | 联合 − XJTU-only |
|---|---:|---:|---:|
| M1 | 1.1768 ± 0.1121 | 1.1768 ± 0.1121 | 0.0000 pp |
| M2 | 2.9973 ± 1.2663 | 3.0159 ± 0.6034 | +0.0185 pp |

M1 的 0.0000 是分域头保留原 XJTU branch 的结果，不是联合数据让 XJTU 变好的证据。M2 在 XJTU 上略有退步，说明共享表示在当前训练预算和来源差异下没有达到“不倒退”。

### MATR OOD transfer

| 方法 | XJTU-only 训练 → MATR OOD | XJTU+MATR source-aware | MAE 降幅 |
|---|---:|---:|---:|
| MLP | 23.6047 pp | 4.5717 pp | 80.63% |
| LSTM | 10.7994 pp | 10.3116 pp | 4.52% |
| LightGBM | 9.8597 pp | 3.8754 pp | 60.69% |

这张表是最直接的“加入 MATR 后在 MATR 上能否工作”证据：MLP 和 LightGBM 获益明显，LSTM 只小幅改善。M1 没有列入 OOD 数字，因为 XJTU-only M1 没有合法的 MATR domain head，运行时应返回 unsupported，而不是伪造跨域预测。

### 相对简单基线的提升

以联合 M1 为参照，在 MATR final 上：

- 比 MLP 低 `2.11896 pp`，相对误差下降 `46.35%`；
- 比 LightGBM 低 `1.42262 pp`，相对误差下降 `36.71%`；
- 比 LSTM 低 `7.85878 pp`，相对误差下降 `76.21%`；
- 比 M2 低 `6.93901 pp`，相对误差下降 `73.88%`。

在 XJTU final 上，MLP 比 M1 低 `0.54296 pp`（`46.14%`），LightGBM 比 M1 低 `0.39484 pp`（`33.55%`）；所以不能写成“联合 M1 在两个来源都领先”。最终选 M1 是针对跨来源联合服务的折中：它在 MATR 的六个 final 电芯上最稳定，并且每个来源都有明确 support/domain 边界；如果只做历史暴露的 XJTU-only 预测，MLP 是更好的数值候选。

## 运行命令和证据文件

以下命令都在仓库根目录执行，使用已经安装的 `model_lab/.venv`，不需要再次访问网络：

```bash
# 生成只含 train/dev/calibration 的开发包和含 final 的一次性比较包
model_lab/.venv/bin/python battery_platform/research/build_joint_bundles.py

# M1/M2 开发阶段（三个 seed；只读取 development bundle）
PYTHONPATH=. model_lab/.venv/bin/python -m model_lab.scripts.v2.train \
  --config battery_platform/research/joint_xjtu_matr/configs/xjtu_matr_m1.yaml
PYTHONPATH=. model_lab/.venv/bin/python -m model_lab.scripts.v2.train \
  --config battery_platform/research/joint_xjtu_matr/configs/xjtu_matr_m2.yaml

# 配方冻结后训练并只打开 final 一次；每个 seed 都保存 no_model_selection_on_this_split=true
PYTHONPATH=. model_lab/.venv/bin/python -m model_lab.scripts.v2.train \
  --config battery_platform/research/joint_xjtu_matr/configs/xjtu_matr_m1_final.yaml

PYTHONPATH=. model_lab/.venv/bin/python -m model_lab.scripts.v2.evaluate \
  --run-id battery_platform/research/joint_xjtu_matr/runs/xjtu_matr_m1_final/M1_joint_seed0 \
  --split final \
  --manifest battery_platform/research/joint_xjtu_matr/bundles/final_comparison/combined/features.json \
  --authorize-final

# 统一跑 MLP/LSTM/LightGBM 与 XJTU-only OOD 诊断
PYTHONPATH=. model_lab/.venv/bin/python battery_platform/research/run_source_aware_baselines_final.py
PYTHONPATH=. model_lab/.venv/bin/python battery_platform/research/run_xjtu_only_transfer_final.py

# 读取所有 JSON 回执并生成三张图
PYTHONPATH=. model_lab/.venv/bin/python battery_platform/research/summarize_joint_benchmark.py
```

上面 M1 final 命令的配置文件在实际目录中分别是 `xjtu_only_m1_final.yaml` 与 `xjtu_matr_m1_final.yaml`；报告保留了每个运行目录的训练/评估回执。一次性 final 运行通过 `--split final --authorize-final`，没有用 final 标签选择 epoch、树数或模型。

主要证据：

- 汇总：`research/joint_xjtu_matr/summary/joint_benchmark_summary_20261002.json`
- 最终性能图：`research/joint_xjtu_matr/summary/final_mae_comparison.png`
- 数据规模图：`research/joint_xjtu_matr/summary/dataset_scale_comparison.png`
- MATR transfer 图：`research/joint_xjtu_matr/summary/matr_transfer_comparison.png`
- 联合基线回执：`research/joint_xjtu_matr/baselines/source_aware_final_20261002.json`
- XJTU-only OOD 回执：`research/joint_xjtu_matr/baselines/xjtu_only_transfer_final_20261002.json`
- M1/M2 各 seed 的 `dev_metrics.json`、`final_metrics.json`、`run.json` 和 `model.json/weights.npz`
- bundle 的源 manifest hash、数组 hash 和 split 行数：`research/joint_xjtu_matr/bundles/*/receipt.json`

## 这次没有做成什么

1. 没有用 final 反复调参。用户要求“多次看测试集”时，能够反复查看的集合被正式改名为 feedback/dev；本报告的 final 只在冻结后读取一次。若未来要根据 final 反馈再调参，必须把它标成 test-feedback，并重新保留一套新的 untouched final，不能继续把同一集合称为盲测。
2. 没有把 LightGBM 冒充 XGBoost。当前环境没有 XGBoost，XGBoost 结果仍是待补实验。
3. 没有把旧 XJTU round3 的 TabICL+ExtraTrees 主模型（开发 MAE 约 `0.5859 pp`）和本阶段 30D XJTU+MATR M1 直接排成一张榜。旧模型使用不同特征/schema、不同窗口和 XJTU-only 协议；它的比较基线另存于 `baselines/development/xjtu_round3_baselines_20261002.json`，不能据此声称已经在 MATR 上验证。
4. 没有声称 M1 是所有来源/所有任务的永久最优。MATR final 只有六个电芯，MLP 在 XJTU 上更好，M2 的共享表示出现负迁移；这些结果完整保留。
5. 没有打开 XJTU 保护的 `*-5` 标签，也没有将本次研究结果写回历史 `model_lab` 数据或旧 final 结果。

## 与其他工作包的统一文档入口

本阶段联合模型只负责数值 SOH 研究。Carbon、Skill、合成内容和 Agent 结果已分别写入独立文档：

- Carbon/经济核算：[V2_CARBON_IMPLEMENTATION.md](V2_CARBON_IMPLEMENTATION.md)
- 16 个 Skill：[V2_SKILLS_DETAIL.md](../../docs/V2_SKILLS_DETAIL.md)
- 2,400 根合成内容与隔离：[V2_CONTENT_IMPLEMENTATION.md](../../docs/V2_CONTENT_IMPLEMENTATION.md)
- Agent A0–A4、GEPA 和 sealed 结果：[V2_AGENT_EXPERIMENT.md](../../docs/V2_AGENT_EXPERIMENT.md)
- 全部提交索引：[根目录 `docs/V2_IMPLEMENTATION_LOG.md`](../../docs/V2_IMPLEMENTATION_LOG.md)

这些文档共同记录了实际做过的内容、失败、限制和验证命令；没有把未运行的 XGBoost、真实专家盲审、现场设备验证或未打开的 sealed 标签写成已完成。
