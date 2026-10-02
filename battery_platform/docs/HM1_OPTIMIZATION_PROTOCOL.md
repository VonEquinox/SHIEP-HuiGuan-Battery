# H-M1 联合模型优化协议

更新时间：2026-10-02

本文定义下一轮联合 XJTU+MATR M1 的结构搜索。它是 development-only 研究协议，不能把 final 反馈当作模型选择依据。代码位于 [`run_hm1_development.py`](../research/run_hm1_development.py)。

## 现有 M1 的问题

当前联合 M1 对每个 `source_id::chemistry::protocol_id` 单独训练三棵 quantile GradientBoostingRegressor。SOH 目标统一取 `log(y)`，每域使用 80 棵、深度 2、最小叶节点 3 的树。这个结构在 MATR 的单一 `matr::LFP::unknown` 域上稳定，但 XJTU 的每个协议域只有少量独立电芯，分域训练会把有限样本切成更小的样本块。

开发集的已知参考均值是：XJTU 约 0.6382 个 SOH 百分点，MATR 约 1.7021 个 SOH 百分点。它说明 MATR 分支已经很强，但 XJTU 仍有结构优化空间。这个参考来自现有 `M1_joint_seed{0,1,2}/dev_metrics.json`，不包含 final 标签。

## 新结构：H-M1

H-M1 由四部分组成：

1. **域专家基线分支。** 每个 `source_id::chemistry::protocol_id` 训练一棵 0.50 quantile GBDT，使用原始 log-SOH。shared/residual/anchor 收缩都为零时，它与现有 M1 的归纳偏置和数值超参一致，因此新结构可以安全回退。
2. **共享 quantile 主干。** 将 30 维统计特征标准化，并附加 source one-hot 和完整 domain one-hot；在 source 内对 `log(SOH)` 做均值/标准差标准化，然后训练共享的 0.05、0.50、0.95 quantile GradientBoostingRegressor。这样 XJTU 的几个协议域可以共享有限样本，同时保留 MATR 与 XJTU 的量纲差异。共享中位数只按 `shared_shrink` 小比例混合到专家预测。
3. **低容量域残差。** 对每个训练域，使用专家中位数预测的残差再训练一棵浅层 Huber GradientBoostingRegressor。残差树最多深度 1，并以 `residual_shrink` 收缩后加回专家分支；训练对象不足 12 个的域不训练残差头，防止单个小域过拟合。
4. **可选 visible-capacity anchor。** 30D 统计视图中的 `recent_capacity_relative_to_reference` 是可解释的退化锚点。候选配置可用 `anchor_shrink` 将 source-normalized 的锚点轻微混合到预测中。锚点只使用训练行拟合的 source 均值/标准差；它不是从 dev 或 final 标签反推的修正。

预测先在 source-normalized log 空间完成，再还原到 SOH 比例。最终展示的 MAE 仍然是按独立电芯宏平均的 SOH 百分点。

## 搜索和门控

`run_hm1_development.py` 的候选网格只在 development bundle 上运行，默认使用 seeds 0、1、2。网格覆盖主干树数量/学习率/深度/叶节点、残差树数量/收缩和 anchor 收缩。每个电芯的多条 landmark 行使用倒数对象频率加权，避免长电芯支配结果。

选择规则已经写入脚本和 `hm1_development_protocol.json`：

- 只按 `dev` 的 cell-macro MAE 排序；`calibration` 只用于稳定性报告，不参与结构选择。
- MATR 门控：候选三 seed 的均值不得高于当前 M1 development 均值 +0.10 pp。
- XJTU 门控：候选三 seed 的均值必须同时严格低于当前 M1 和同一 development bundle 的 MLP 均值。
- 同时通过两个门控时，以 `XJTU_MAE + 0.2 × MATR_MAE` 排序。若没有候选通过，保留现有 M1，不得为了好看的结果放宽门控。

这些是 development 目标，不是 final 结果保证。即使候选通过，也必须冻结候选、实现可验证的数值导出，再把完整训练流程固定后对 final 运行一次。`run_hm1_development.py` 会拒绝包含 `final`、`final-test`、`sealed` 或 `protected` 行的 bundle，并在 JSON 回执中写入 `final_labels_used: false`。

## 推荐运行方式

```bash
cd /Users/vonequinox/Program/GithubProjects/SHIEP-HuiGuan-Battery
PYTHONPATH=. model_lab/.venv/bin/python \
  battery_platform/research/run_hm1_development.py \
  --bundle battery_platform/research/joint_xjtu_matr/bundles/development/combined/features.json \
  --output battery_platform/research/joint_xjtu_matr/hm1_development
```

快速检查可加 `--limit 2`，但快速检查不能用于选择最终结构。完整运行后应检查：

```bash
model_lab/.venv/bin/python -m json.tool \
  battery_platform/research/joint_xjtu_matr/hm1_development/hm1_development_results.json >/dev/null
```

## 当前状态和限制

截至本文更新时间，H-M1 只有结构和 development runner，尚未运行完整候选网格，也没有 final 分数。因此不能声称它已经超过 MLP 或已经在 MATR 上保持 SOTA。为检查 specialist 分支的数值回退关系，曾用 `n_estimators=80`、专家学习率 0.1、深度 2、叶节点 3、所有新分支收缩为 0 做 development smoke check；三 seed 的均值约为 XJTU 0.6034 pp、MATR 1.6529 pp。这只是本地结构诊断，不是预注册网格选择，也没有接触 final 标签。后续若通过门控，必须补充：候选逐 seed development 分数、与 MLP 的同 bundle 对照、固定模型导出/回放误差，以及一次性 final 回执。

MATR 的 30D bundle 是 capacity-history statistics 视图，没有与 XJTU 完全相同的实测曲线输入；H-M1 的共享主干因此只使用对两源都存在的统计特征和来源适配器。XJTU 的受保护 `*-5` 电芯仍然不在该实验中。
