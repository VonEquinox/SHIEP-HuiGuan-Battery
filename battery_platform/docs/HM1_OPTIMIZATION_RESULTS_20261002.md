# 联合 H-M1 结构优化结果（2026-10-02）

本文记录联合 XJTU+MATR M1 的结构修改、候选搜索、开发集结果和导出验证。所有结构选择只读取
`bundles/development/combined/features.json`；该包只有 train/dev/calibration 行。XJTU 受保护的 `*-5`
电芯以及历史 comparison final 没有被此轮优化器读取，因此这里的数字是 development 结果，不能写成新的
盲测或外部领域 SOTA 证明。

后续 F01 温度有效性修复另建了六通道特征版本，并以同一开发人口独立重训 H-M1/M1/M2。
新 H-M1 的标量输入与开发 MAE 保持不变；新旧 schema、权重绑定、扫描分母及 M2 退化结果见
[F01 独立重训记录](F01_CHANNEL_VALIDITY_RETRAIN_20261002.md)。下文保留原结构优化阶段的版本与指标。

## 为什么要改 M1

旧联合 M1 是按 `source_id::chemistry::protocol_id` 分域训练的 quantile GBDT。每个 XJTU 协议都只有少量
独立电芯，训练样本被切成三个小 head；MATR 则主要落在一个域。这个分域边界保护了 MATR 的稳定性，
但没有让 XJTU 的协议共享统计规律。旧 M1 在 development 的 cell-macro SOH MAE 是：XJTU `0.6095 pp`、
MATR `1.7021 pp`。同一 development bundle 的 source-aware MLP 参考是 XJTU `0.7297 pp`、MATR `5.3303 pp`。
这两个参考用于预登记门控，不使用 final 标签。

## 结构演进

第一轮实现了一个有回退路径的层级 H-M1：保留按域的 q50 专家，增加 source 共享 quantile 主干、浅层
source/domain residual 和可选的 recent-capacity anchor。它用 source-normalized `log(SOH)` 训练，并按
物理电芯对 landmark 行做倒数加权。128 个候选、3 个 seed 的完整回执在
[`hm1_development_results.json`](../research/joint_xjtu_matr/hm1_development/hm1_development_results.json)。
修正专家学习率为当前 M1 实际值 `0.10` 后，最优层级候选达到 XJTU `0.5210 pp`、MATR `1.5610 pp`，同时通过两项 development 门控；早先用错误学习率生成的回执已被覆盖，不再作为证据。

根据这轮诊断，最终冻结的研究候选简化为更容易验证的 **source-level pooled quantile backbone + source-level
residual**，仍属于 H-M1 家族：

1. 对每个 source（XJTU、MATR）把所有 protocol/domain 的 train 行合并，分别训练 q05、q50、q95 三个
   `GradientBoostingRegressor`；树数 160、最大深度 3、最小叶 5、学习率 0.03。
2. 目标是 source 内标准化的 `log(SOH)`。标准化均值/尺度只从 train 计算，推理时再指数还原。
3. 对每个 source 的 q05/q50/q95 主干预测残差，再训练 80 棵、深度 2、最小叶 5、学习率 0.03 的浅层
   quantile GBDT，并以 residual weight `1.0` 加回。它是 source-level residual，不冒充每个协议都有独立
   adapter。
4. train 行按独立电芯做 cell-balanced 权重；q05/q50/q95 输出按行排序，保证区间顺序。q50 是点预测，
   q05/q95 只用于区间输出和稳定性诊断。

这样改的目的有两个：XJTU 的小协议 head 可以共享 source 内的统计规律，MATR 仍然保留自己的 source
归一化和 residual；同时保留原 M1 的量化输出契约，而不是用只返回 q50 的树模型替代 M1。

## 候选搜索与门控

宽搜索文件 [`hm1_development_candidates_20261002.json`](../research/joint_xjtu_matr/optimization/hm1_development_candidates_20261002.json)
共记录 1,440 个配置/seed 组合；短列表文件
[`hm1_selected_development_20261002.json`](../research/joint_xjtu_matr/optimization/hm1_selected_development_20261002.json)
记录 36 个配置/seed 组合。两者都写入 `final_labels_used_for_selection: false`，并拒绝
`final`、`final-test`、`sealed`、`protected` split。

预登记门控为：

- 只按 dev 的 source cell-macro MAE 选择；calibration 只报告稳定性。
- MATR 三 seed 均值不高于旧 M1 development `1.7021 + 0.10 pp`。
- XJTU 三 seed 均值同时严格低于旧 M1 `0.6095 pp` 和同包 MLP `0.7297 pp`。
- 通过后以 `XJTU_MAE + 0.2 × MATR_MAE` 排序；没有通过者就保留旧 M1。

ExtraTrees 的 q50 点预测在 XJTU 可到约 `0.24–0.29 pp`，但 MATR 为约 `1.90–2.42 pp`，且没有 q05/q95
导出契约，所以没有被选为 M1。GBDT d3/l2 和 d3/l5 都通过短列表门控；d3/l5 在预登记组合目标下更优，
随后以同一超参补跑完整 q05/q50/q95 版本。

## 完整量化候选结果

机器可读回执为 [`hm1_quantile_development_20261002.json`](../research/joint_xjtu_matr/optimization/hm1_quantile_development_20261002.json)，
三份可重载模型为 `optimization/hm1_quantile_models_20261002/seed{0,1,2}.json`。误差单位为 SOH percentage
points，先按独立电芯求 MAE，再对电芯宏平均；均值后面的数字是 3 个 seed 的样本标准差。

| split / source | q50 MAE (pp) | q50 RMSE (pp) | 90% coverage | 区间宽度 (pp) |
|---|---:|---:|---:|---:|
| dev / XJTU | **0.3841 ± 0.0173** | 0.4810 ± 0.0261 | 0.9583 ± 0.0000 | 8.9372 ± 0.1595 |
| dev / MATR | **1.5290 ± 0.0344** | 3.9254 ± 0.0540 | 0.8125 ± 0.0208 | 12.8174 ± 0.1375 |
| calibration / XJTU | 0.6944 ± 0.0427 | 0.9831 ± 0.0150 | 0.7292 ± 0.0361 | 9.6395 ± 0.2088 |
| calibration / MATR | 0.1751 ± 0.0264 | 0.3285 ± 0.0587 | 0.9306 ± 0.0241 | 16.9896 ± 0.3415 |

逐 seed 的 dev q50 MAE 是：

| seed | XJTU (pp) | MATR (pp) |
|---:|---:|---:|
| 0 | 0.3932 | 1.5623 |
| 1 | 0.3642 | 1.5311 |
| 2 | 0.3950 | 1.4935 |

对应的 development-only 柱状图见 [`hm1_development_comparison.png`](../research/joint_xjtu_matr/optimization/hm1_development_comparison.png)。

相对同一 development bundle 的参考，XJTU 比旧 M1 降低 `0.2254 pp`（约 `36.98%`），比 source-aware MLP
降低 `0.3456 pp`（约 `47.36%`）；MATR 比旧 M1 降低 `0.1732 pp`（约 `10.18%`），比 MLP 降低
`3.8013 pp`（约 `71.32%`）。这些百分比只描述本次 development 比较，不能外推成 final 或公开基准排名。

## 导出和重放验证

每个 seed 的 JSON 包含：特征 median/mean/scale、source log 均值/尺度、三个 quantile 主干树、三个 residual
树以及超参。训练脚本随后从 JSON 数值树重新推理整个 bundle，三 seed 的 `replay_max_abs_soh` 均为 `0.0`。
这证明当前研究包的树数值与 Python 训练对象一致；它还没有接入生产 `DomainBaseline.from_dict` 的完整
efficiency/survival/fault 模型契约，因此当前状态是 **H-M1 quantile research prototype**，不是已发布的
生产模型版本。

## 选择结论与下一步边界

在 development gate 下，冻结候选是 source-level pooled q05/q50/q95 GBDT 加 source-level residual，
而不是 ExtraTrees，也不是第一轮保守的 protocol-specialist H-M1。它已经同时超过同包 MLP 的 XJTU development
分数，并保持 MATR 低于旧 M1 development 误差，满足本轮用户目标的内部实验判据。

这仍不能写成“最终 SOTA”：历史 comparison final 已经被上一阶段读取，且 XJTU `*-5` 受保护电芯不能在本
协议下打开。若要得到新的无偏 final 数字，需要在不读取保护标签的前提下重新建立 untouched object-level
final、冻结本配方、运行一次，并把 final 回执和任何 test-feedback 分开命名。当前文档不会把历史 final 的
MLP/M1 数字与本轮 development 数字混成一张排行榜。

运行命令：

```bash
PYTHONPATH=. uv run --project . python battery_platform/research/run_hm1_quantile_development.py
PYTHONPATH=. uv run --project . python battery_platform/research/run_hm1_selected_development.py
```
