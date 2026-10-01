# MATR 完整 corrected 物理生命周期开发结果

执行日期：2026-10-02。此实验为 development_only_research，validated_deployment=false，只有 train/dev/calibration，final=0。它验证真实生命周期头可运行及删失语义，不证明发布论文复现、独立来源泛化、寿命概率校准或部署准确性。

固定 50/100/200 物理循环 query、输入严格早于 query、8条历史×64点、M2 width128/adapter32、min_survival_objects=2、epochs12、三种子0/1/2、M1 joint 与 M2 joint/no_domain_adapter/no_history/SOH single_task。全部 15 runs 按 preregistration.json 完成，模型参数/损失/输入没有根据开发成绩改变。

## 身份、删失和域

完整 MAT 身份资格：140 structs、135独立 barcode、5真实续测、134有测量对象，0.88 Ah strictly_less_than 下43 exact/91 right。新特征开发人口为123对象（79 train /23 dev /21 calibration）与368窗口（128 exact/240 right）。六个历史 final 在数值投影前排除，5个跨续测 policy 改变对象排除，原采集异常和已死亡 query 明确记录；不通过 pool policy 增加样本。

68个精确 policy 中17个有至少2个独立 train 生存对象；dev 中6个域满足研究支持，8个独立对象（1 exact/7 right）可评分。重复窗口不是新增独立电芯。M1有6个 dev SOH 域，M2有12个；RUL比较仅使用下面共同6域。

## 每域 RUL censored NLL

均值 ± 三种子样本标准差；等对象权重后在对象内平均固定 query。右删失-only 域的近零 NLL 只说明模型把概率放在观察窗之后，不能说明其未观察 EOL 的预测正确。M1 hazard 优化无随机步骤，因此三种子相同。

| 精确源 policy | dev对象 | right比例 | M1 joint | M2 joint | M2 no adapter | M2 no history |
|---|---:|---:|---:|---:|---:|---:|
| 4.8C(80%)-4.8C | 1 | 0% | 2.37817 ± 0 | 0.968311 ± 0.0779 | 1.23461 ± 0.187 | 0.974701 ± 0.108 |
| 4.8C(80%)-4.8C-newstructure | 2 | 100% | 0.00178601 ± 0 | 0.143095 ± 0.0596 | 0.233242 ± 0.0971 | 0.178633 ± 0.00565 |
| 5.3C(54%)-4C-newstructure | 2 | 100% | 0.000998129 ± 0 | 0.0851901 ± 0.0241 | 0.168599 ± 0.0662 | 0.0887189 ± 0.0174 |
| 5.6C(19%)-4.6C-newstructure | 1 | 100% | 0.00121707 ± 0 | 0.116599 ± 0.0221 | 0.179201 ± 0.0513 | 0.122973 ± 0.0206 |
| 5.6C(36%)-4.3C-newstructure | 1 | 100% | 5.52841e-05 ± 8.3e-21 | 0.0745013 ± 0.00527 | 0.144029 ± 0.0505 | 0.0740214 ± 0.0171 |
| 5C(67%)-4C-newstructure | 1 | 100% | 0.000331943 ± 6.64e-20 | 0.123963 ± 0.0368 | 0.207647 ± 0.128 | 0.145036 ± 0.0336 |

所有可比较域的 C-index 均为 null：没有不同独立对象、同 query、已知可排序事件边界的合法对。仅一个 exact dev 电芯不能证明寿命排序能力。JSON 保留每 horizon 的 object-averaged known-status Brier、n_known/n_known_objects；它没有 IPCW 或概率校准保证，删失未来不当失败评分。exact T=t 时 S(t)=P(T>t) 的真值为0；right/interval 的开放下界等于t仍为存活。比较排除同对象、不同 query 起点。SOH single_task 的 RUL/risk 全部 unsupported。

## 同六域 SOH MAE（百分点）

| 精确源 policy | M1 joint | M2 joint | M2 no adapter | M2 no history | M2 SOH single |
|---|---:|---:|---:|---:|---:|
| 4.8C(80%)-4.8C | 0.127685 ± 0.0087 | 2.71861 ± 3.34 | 1.86254 ± 1.93 | 2.78541 ± 3.03 | 1.88807 ± 0.447 |
| 4.8C(80%)-4.8C-newstructure | 0.100865 ± 0.00478 | 4.03857 ± 4.3 | 1.41686 ± 1.13 | 5.38743 ± 2.33 | 1.26454 ± 1.04 |
| 5.3C(54%)-4C-newstructure | 0.114998 ± 0.0134 | 1.52371 ± 1.2 | 2.83592 ± 1.57 | 5.38725 ± 2.11 | 1.15227 ± 0.155 |
| 5.6C(19%)-4.6C-newstructure | 0.0460875 ± 0.007 | 2.06226 ± 1.14 | 2.78973 ± 1.58 | 4.4405 ± 1.15 | 1.36885 ± 0.573 |
| 5.6C(36%)-4.3C-newstructure | 0.145693 ± 0.00812 | 3.45427 ± 3.14 | 3.76061 ± 1.58 | 3.8996 ± 2 | 0.664569 ± 0.627 |
| 5C(67%)-4C-newstructure | 0.0178332 ± 0.00299 | 3.9521 ± 2.19 | 2.28795 ± 1.29 | 5.20327 ± 1.88 | 1.63766 ± 0.668 |

M2的SOH劣化如实保留。早期容量接近固定参考且每域只有1–2 dev对象，M1小误差也不代表全寿命或跨policy泛化。完整20个dev policy的可评/不可评状态、每对象MAE/RMSE、分位损失、NLL、Brier、CQR范围见 dev_summary.json 和每 run dev_metrics.json；没有按表现挑域作为主交付。

## 校准与泄漏边界

每精确 policy 的合法 calibration 对象最多2个，α=0.2的80% object-max CQR有限样本rank不足，全部为 insufficient_calibration_objects / unbounded。未生成有限80%覆盖保证。RUL/risk 是同一 hazard 的生存分布与1−S(H)，calibration_version=null；未拟合寿命校准器。efficiency/fault无合法源标签，始终unsupported。

旧容量摘要 train/dev/calibration 与本次共有29对象：旧train17→新train17；旧dev5→新train、旧dev1→新dev；旧calibration6→新dev。六个旧final重叠为0。该暴露历史意味着本开发比较不能声称干净独立来源泛化；overlap_receipt.json 完整记录。

初始 32×256 feature 包从未 fit，只作为资源规划记录。首个15-run矩阵 matr_lifetime_development_20261002 在代码审查发现离线M2未知policy fallback问题后标记 superseded_before_final；原 metrics、校准、模型hash保留，不作为选择或最终支持证据。package guard 当时已拒绝未知policy。纠正版仅增加未知policy的全头缺失遮罩，用相同数据、参数、种子重跑本矩阵；没有根据分数改配置或消费任何 final。

## 实际命令与安全重载

```bash
uv run python -m model_lab.scripts.v2.lifetime_features \
  --derived model_lab/data/derived/v2/matr_corrected_development_20261002 \
  --out model_lab/data/derived/v2/replay_matr_lifetime_budgeted \
  --query-prefixes 50 100 200 --history 8 --points 64 \
  --exclude-identity-manifest model_lab/data/derived/v2/multisource_features_20261002_v2/features.json
uv run python -m model_lab.scripts.v2.train --config model_lab/configs/model_v2_matr_lifetime_masked.yaml
uv run python -m model_lab.scripts.v2.calibrate --run-id model_lab/reports/v2/matr_lifetime_development_masked_20261002/M2_joint_seed0 --alpha 0.2
uv run python -m model_lab.scripts.v2.evaluate --run-id model_lab/reports/v2/matr_lifetime_development_masked_20261002/M2_joint_seed0 --split dev
uv run python -m model_lab.scripts.v2.summarize --directory model_lab/reports/v2/matr_lifetime_development_masked_20261002 --split dev
uv run python -m model_lab.scripts.v2.verify_package \
  --package model_lab/reports/v2/packages/M1_matr_lifetime_masked_seed0 \
  --package model_lab/reports/v2/packages/M2_matr_lifetime_masked_seed0
```

输出目录/校准文件已存在会明确拒绝；实际复现训练需将配置复制到新的 preregistered output，不覆写历史记录。完整source资格重放需要ignored原始MAT；已提交1.9MB预算开发特征与包内真实无标签dev输入允许fresh checkout的研究训练/推理，无须原始8GB。包为唯一版本 matr_lifetime_development_masked_20261002:M1_joint_seed0 / M2_joint_seed0，固定seed0展示不做最佳种子选择。两包各21个真实dev输入（首个＋20个域），包含supported/unsupported，不含未来标签状态或数值标签，profile整体重放容差1e-7。六包合并回执见 package_replay_with_lifetime_units_20261002.json。

所有新profile保持validated_deployment=false，不能作为Carbon已验证生命周期/效率输入，也不自动替代原四个已集成模型包。公开数据许可与引用见 sources/DELIVERY.md；真实原始MAT、整网页/整脚本及作者源码仍只读本地，缓存移动回执保存原路径/hash，不删原始文件。

Phase17 最终元数据复核将 threshold_risk 的 unit 从继承的 physical_cycle 改为 probability；风险 H 仍按物理循环、RUL unit 仍 physical_cycle。只修两份新增研究包的保存profile及相应hash，逐项归一化比较证明全部数值不变，原四包与训练/指标不改。unit_metadata_correction.json 保留修正前后模型和manifest hash；修正后六包再次完整1e-7重放通过。先前回执保留为修正前历史记录，最新回执使用 units 后缀。
