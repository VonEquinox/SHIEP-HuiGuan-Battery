# H-M1 联合模型优化协议

更新时间：2026-10-02

本文定义联合 XJTU+MATR M1 的 development-only 结构搜索。代码入口是
[`run_hm1_development.py`](../research/run_hm1_development.py)，完整量化候选入口是
[`run_hm1_quantile_development.py`](../research/run_hm1_quantile_development.py)。本协议不会读取
`final`、`final-test`、`sealed` 或 `protected` 行；历史 final 反馈不参与本轮选择。

## 现有 M1 与优化目标

现有联合 M1 对每个 `source_id::chemistry::protocol_id` 单独训练 q05/q50/q95 quantile
GradientBoostingRegressor，SOH 目标是 `log(y)`，每域 80 棵、深度 2、最小叶 3。XJTU 的每个协议域只有
少量独立电芯，分域会把可共享的统计规律切开；MATR 的单一域则相对稳定。

development 的 cell-macro 参考来自现有 `M1_joint_seed{0,1,2}/dev_metrics.json` 的逐电芯
`per_object`：XJTU `0.6095 pp`、MATR `1.7021 pp`。同包 source-aware MLP 的 XJTU 参考为
`0.7297 pp`，MATR 为 `5.3303 pp`。候选必须同时严格优于旧 M1 和 MLP 的 XJTU 参考，且 MATR 不得比
旧 M1 高出 `0.10 pp`。

## H-M1 结构

第一轮预登记结构包含四部分：按域的 q50 专家、source 共享 q05/q50/q95 主干、浅层 residual、可选的
recent-capacity anchor。它以 source-normalized `log(SOH)` 训练，按独立电芯对 landmark 行做 cell-balanced
加权，shared/residual/anchor 收缩为零时保留原 M1 的回退路径。

第一轮的 128 个候选、384 个 seed 记录见
[`hm1_development_results.json`](../research/joint_xjtu_matr/hm1_development/hm1_development_results.json)。
修正专家学习率为当前 M1 实际值 `0.10` 后，其最优均值为 XJTU `0.5210 pp`、MATR `1.5610 pp`，通过两项门控；随后继续比较 source-level 量化候选。

随后采用同一 H-M1 思路中更容易验证的 source-level 版本作为研究候选：

1. XJTU 和 MATR 分别把各自 protocol/domain 的 train 行合并，训练 q05/q50/q95 GBDT 主干；160 棵树、
   深度 3、最小叶 5、学习率 0.03。
2. 在每个 source 内标准化 `log(SOH)`，所有标准化量只由 train 计算。
3. 对每个 source 的三个 quantile 主干残差再训练 80 棵、深度 2、最小叶 5、学习率 0.03 的 quantile
   residual GBDT，residual weight 为 1.0。
4. 训练行按物理电芯倒数频率加权；输出 q05/q50/q95 按行排序以保证区间顺序。q50 用作点预测，q05/q95
   用作区间诊断。

这个 source-level residual 不是每个协议单独的 adapter；它通过 source 内共享样本降低小 XJTU head 的
方差，同时保留 XJTU 与 MATR 的 source 归一化边界。

## 搜索、门控和验证

宽搜索 [`hm1_development_candidates_20261002.json`](../research/joint_xjtu_matr/optimization/hm1_development_candidates_20261002.json)
记录 1,440 个配置/seed 组合；短列表
[`hm1_selected_development_20261002.json`](../research/joint_xjtu_matr/optimization/hm1_selected_development_20261002.json)
记录 36 个配置/seed 组合。选择只按 dev 的 source cell-macro MAE 排序；calibration 只报告稳定性。
GBDT d3/l2 与 d3/l5 均通过初始门控，ExtraTrees 虽然 XJTU 约 `0.24–0.29 pp`，但 MATR 约
`1.90–2.42 pp`，且没有完整 q05/q95 契约，所以不选。

最终 d3/l5 配方补跑完整量化脚本后，机器可读回执为
[`hm1_quantile_development_20261002.json`](../research/joint_xjtu_matr/optimization/hm1_quantile_development_20261002.json)，
三份树模型位于 `optimization/hm1_quantile_models_20261002/`。三 seed dev q50 均值为 XJTU
`0.3841 ± 0.0173 pp`、MATR `1.5290 ± 0.0344 pp`；JSON 数值树重放最大误差为 `0.0`。
完整逐 seed、区间 coverage、宽度、失败结构和限制见
[`HM1_OPTIMIZATION_RESULTS_20261002.md`](HM1_OPTIMIZATION_RESULTS_20261002.md)。

## 状态与边界

当前选中的是 development 内部的 H-M1 quantile research prototype。它同时低于旧 M1 和 MLP 的 XJTU
development 参考，并保持 MATR 低于旧 M1 development 误差；这满足本轮内部门控，但不能写成公开领域
SOTA 或新的 final 结论。当前 JSON 尚未接入生产 `DomainBaseline.from_dict` 的完整 efficiency/survival/fault
契约。

若要取得新的无偏 final，必须在冻结此配方后建立不含受保护标签的 untouched object-level final，随后只运行
一次并单独记录 final/test-feedback。当前协议不打开 XJTU `*-5` 电芯，也不把历史暴露 final 与本轮
development 数字混成排行榜。

推荐命令：

```bash
PYTHONPATH=. uv run --project . python battery_platform/research/run_hm1_development.py
PYTHONPATH=. uv run --project . python battery_platform/research/run_hm1_quantile_development.py
```
