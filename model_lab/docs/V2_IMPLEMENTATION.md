# V2 numerical/data implementation record

Date: 2026-10-02 (Asia/Shanghai). This is an additive `model_lab` V2 research namespace. V1 models, artifacts, splits, and the three protected XJTU `*-5` cells remain untouched. No protected cell was opened, hashed, transformed, trained on, calibrated, or scored.

## Data and provenance

`model_lab/modeling/v2/data.py` provides source-preserving contracts and guarded MATLAB/HDF5/CSV/Parquet readers. Pickle/joblib loading is rejected, HDF5 links are rejected, raw files are hash recorded, and every exclusion is persisted. XJTU cycles preserve source ordinal and set `physical_cycles_known=false`; this prevents an ordinal from silently becoming a RUL cycle. Measured XJTU SOH targets use a frozen first observed diagnostic reference. RUL, efficiency, and fault labels remain unavailable unless a source supplies verified physical time/threshold, complete metering boundaries, or confirmed root-cause labels.

`model_lab/modeling/v2/sources.py` and `scripts/v2/ingest.py` maintain a YAML registry with official landing/resolved links, retrieval time, license status, bytes, author checksum and SHA-256. Retrieval uses `http://127.0.0.1:7897`. All four sources now have actual parsed data with explicitly limited `raw_scope`: XJTU measured RPT/curves; one complete MATR Arbin cell and official 2018 capacity-summary measurements; DyAD brand-3 vehicle snippets; CH public generated fault data. Detailed counts, exclusions, actual download attempts, license receipts, and commands are in `model_lab/reports/v2/sources/DELIVERY.md`. Full raw downloads and full official HTML/JavaScript stay local; small official JSON, license summaries, URLs and hash receipts enter version control. XJTU, MATR and DyAD retain observed CC BY 4.0 metadata; CH retains CC BY-NC-SA 4.0 and the provider's academic/non-commercial/additional redistribution terms. CH raw data is not uploaded.

`model_lab/data/derived/v2/xjtu_development_20261001/` contains 18 measured development/calibration objects (12,170 source records, 581 bounded diagnostic segments, 1,972 measured SOH targets) and three final identities retained filename-only before model freeze. Split is frozen before raw parsing: 11 train, 3 dev, 4 calibration, 3 final. Feature construction at `model_lab/modeling/v2/features.py` makes prefix-only landmarks: visible records are strictly before the query; each reference is frozen from that object’s already-visible first RPT; normalization is fitted only on train objects; future capacity, terminal records, source `cycle_life`, and sealed final data never enter a training view.

## Models and contracts

M1 (`baselines.py`) is a per-source/chemistry/protocol probabilistic baseline: quantile gradient-boosting SOH/efficiency heads, optional NGBoost Normal serialization, fault GBDT, and a discrete hazard model that handles exact, right-censored, and interval-censored outcomes. It exports JSON tree arrays and never deserializes arbitrary pickle. M2 (`multitask.py`) is a masked width-128 temporal encoder with per-domain 128→32→128 residual adapters and separate SOH, efficiency, survival, and fault heads. Missing labels are masked; absent labels produce no supervision or supported prediction. Actual missing curves use an all-zero sequence mask and statistical input, not synthetic curves. Ablations are joint, no-domain-adapter, no-history, and SOH single-task. No-history removes only the source's explicitly identified historical-capacity columns; it does not erase arbitrary DyAD current temperature statistics.

`prediction.py` implements `battery_prediction_v2`: every head carries support, target definition, unit, horizon, distribution kind, parameters/quantiles, calibration version, and evidence references. `unsupported` is a valid result. `model_lab/scripts/v2/export.py` creates a checksummed safe JSON/NPZ package and reloads it to numerical tolerance; no user-uploaded model is loaded. Packages contain actual label-free development samples, with only features/sequences/masks/domain arrays and their query metadata, so a fresh checkout can inspect supported and unsupported heads without raw files or final features. `calibration.py` performs object-grouped CQR on the independent calibration split and records finite-sample resolution. With small calibration domains, the result is explicitly unbounded/insufficient rather than a false 95% claim.

M1's primary reported distribution is the q05/q50/q95 quantile GBDT plus CQR; MAE/RMSE use its q50 point estimate. Separately trained NGBoost log-SOH or logit-efficiency Normal parameters appear as `alternative_distribution` and have no inherited CQR calibration claim. `nll_original_scale` evaluates that explicitly separate NGBoost distribution including the transformation Jacobian; it is not the NLL of the quantile GBDT. M2 quantiles and transformed-Normal parameters come from the same head. Survival median, threshold probability and survival function come from one hazard distribution; a median beyond the grid is `null/exceeds_prediction_range`. Beyond-grid observed events are right-censored at the grid instead of forced into the last event bin.

## Reproducible commands and evidence

```bash
.venv/bin/python -m model_lab.scripts.v2.ingest --source all --metadata-only --config model_lab/configs/data_v2.yaml
.venv/bin/python -m model_lab.scripts.v2.features --derived model_lab/data/derived/v2/xjtu_development_20261001 --out model_lab/data/derived/v2/xjtu_features_protocol --landmarks 8
.venv/bin/python -m model_lab.scripts.v2.train --config model_lab/configs/model_v2.yaml
.venv/bin/python -m model_lab.scripts.v2.calibrate --run-id model_lab/reports/v2/xjtu_development_20261002/M1_joint_seed0
.venv/bin/python -m model_lab.scripts.v2.evaluate --run-id model_lab/reports/v2/xjtu_development_20261002/M1_joint_seed0 --split dev
.venv/bin/python -m model_lab.scripts.v2.export --run-id model_lab/reports/v2/xjtu_development_20261002/M1_joint_seed0 --out model_lab/reports/v2/packages/M1_joint_seed0_complete
.venv/bin/python -m model_lab.scripts.v2.train --config model_lab/configs/model_v2_multisource_fixed.yaml
.venv/bin/python -m model_lab.scripts.v2.calibrate --run-id model_lab/reports/v2/multisource_fixed_loss_20261002/M1_joint_seed0 --alpha 0.2
.venv/bin/python -m model_lab.scripts.v2.evaluate --run-id model_lab/reports/v2/multisource_fixed_loss_20261002/M1_joint_seed0 --split final --authorize-final
.venv/bin/python -m pytest model_lab/tests/v2 -q
```

Evidence: `model_lab/reports/v2/xjtu_development_20261002/preregistration.json`, each run's `run.json`, `dev_metrics.json`, `calibration.json`, and `dev_summary.json`. Three seeds are retained for every preregistered family/ablation. The dev result is not a public benchmark and does not establish cross-chemistry transfer. The independently released final bundle was evaluated exactly once after all 15 model recipes froze. Final R3 (two objects) M1 MAE is 1.819 ± 0.188 percentage points, M2 joint is 2.547 ± 1.608; final RW (one object) M1 is 0.535 ± 0.064, M2 joint is 3.263 ± 1.305. The fixed split contains no satellite final object. M2 did not improve this comparison. Single-task and joint match because only SOH labels are available. All 15 results and ablations remain in `final_summary.json`; the final result did not trigger model tuning. Unbounded CQR mathematically covers every target and is not evidence of useful calibration.

The supported experimental heads are measured XJTU SOH, MATR capacity-reference SOH, and DyAD retrospective vehicle-anomaly classification. DyAD chemistry remains `unknown`, its native channel units are unverified, and its local timestamp is not promoted to a global clock. These data do not establish cell root-cause classification. RUL/efficiency/fault support remains unavailable on XJTU; MATR summary ordinal cannot provide physical-cycle RUL. The single complete MATR Arbin cell does have 542 explicit `Cycle_Index` cycles and a genuine 0.88 Ah event/censoring target, but one cell does not establish independently validated deployable lifetime prediction. The three corrected MATLAB batches and published 124-cell lifetime benchmark have not been reproduced; `paper_reproduction.json` records this block. Efficiency requires complete metering/SOC boundaries; no current fitted package claims it. Such outputs remain unsupported and cannot feed carbon accounting as validated lifetime/efficiency parameters.

## Runtime reproducibility

`training_environment.json` records the actual versions used by the 15 runs (including scikit-learn 1.9.1). The root UV runtime subsequently pins scikit-learn 1.7.2 to preserve V1 artifact compatibility. V2 inference exports are numeric JSON/NPZ and do not load sklearn pickle. Exact V2 retraining can use `model_lab/scripts/v2/setup_training.sh` to install the pinned `model_lab/configs/v2_training_requirements.txt` into an isolated, ignored local `.venv` beneath reports/v2/runtime; this does not alter the V1 environment.

The corrected multisource matrix records its actual later root UV environment (scikit-learn 1.7.2) separately. Run records are immutable historical hash/parameter receipts. Commands reject existing output directories and repeat final access; reproducing training requires a new preregistered output directory. No raw bulk, final feature bundle or local environment enters the commit. The tracked XJTU development bundle is `model_lab/data/derived/v2/xjtu_features_protocol/features.json` and `features.npz`, contains exactly 18 development/calibration objects and no new V2 final or protected identity, and uses a relative array filename. Package reload needs only relative safe package files. Historical source paths in receipts remain traceable evidence and are not runtime dependencies.

## M0 原支持域回归（不编造数值对照）

M0 保留原冻结 ExtraTrees/混合模型、`xjtu_71d_partial_cc_v1` 输入和原来的 NCM CC 前缀支持范围。根集成在兼容的 scikit-learn 1.7.2 / TabICL 2.2.0 环境重跑原 V1 后端 28 项回归，结果见 `docs/V2_IMPLEMENTATION_LOG.md` 的“V1 模型兼容与一键运行补齐”。本次 Web `platform.spec.ts` 3 个真实用例通过，包含原模型真实推理→告警→派单→现场证据→独立验收→重载持久化，见 `docs/V2_WEB_IMPLEMENTATION.md` 的 E-WEB-03。它是 M0 原支持域的实际功能回归证据。

本模块没有重新构造 M0 的 MAE/RMSE 或 M0 与 M1/M2 的干净独立数值对照。新 V2 三个 final 对象来自原 V1 开发人口，M0 原来使用过这些对象，因此不能把它们当成 M0 未见过的测试。三个原保护 `*-5` 电芯仍封存。M0 不能因为加入 MATR 而被要求支持 LFP。

## 固定损失修复与实验留痕

`multisource_20261002` 是保留的开发试运行，尚未执行 final。代码审查发现它按当前 minibatch 中可用头数重新取平均，缺失标签会改变任务相对权重。修复版 `multisource_fixed_loss_20261002` 使用固定来源权重、物理对象/可见时间归一化和固定任务 λ；缺标签只贡献零，不因头缺失而重新分配权重。所有不可用标签均被遮罩，并新增验证测试。旧试运行完整保留，`pilot_status.json` 说明取代原因；没有用其结果进行最终选优。

修复后的新实验使用 XJTU 18 个开发/校准对象、MATR 35 个有效原始条码和 DyAD 100 个原始车辆。MATR 已登记 36 个条码，其中一个官方采集问题对象不产生有效特征；36 和 35 的分母分别记录。MATR 曲线缺失时只使用原始容量历史，DyAD 原始通道单位未核验时只使用统计输入；两者都不补造真实曲线。DyAD 监督是车辆异常二分类，不是单电芯根因；模型头按来源遮罩，不能把共享表示自动变成其他来源的 SOH 或故障标签。

新实验的 XJTU 旧 final 完全不在组合包中。新的 final 仅为第一次比较的 MATR/DyAD 对象，完成后不再次调参。校准 α 在配置中预先定为 0.2；MATR 六个独立校准对象允许有限分辨率的 80% 区间，XJTU 小域仍可能无界。DyAD 校准使用每个车辆的固定首个 landmark，类别独立对象不足时保持未校准，不伪造概率置信度。

## 三种子多源实际结果

`multisource_fixed_loss_20261002` 的 15 个模型全部完成训练、独立校准和首次 final；结果为种子 0/1/2 的均值 ± 样本标准差，未以 final 选种子或再调参。

| 模型 | MATR dev SOH MAE（百分点） | MATR final SOH MAE（百分点） | DyAD dev 车辆 AUCPR | DyAD final 车辆 AUCPR |
|---|---:|---:|---:|---:|
| M1 per-domain | 1.702 ± 0.008 | 2.453 ± 0.007 | 0.750 ± 0 | 0.333 ± 0 |
| M2 joint | 10.175 ± 0.563 | 9.920 ± 0.780 | 0.861 ± 0.127 | 0.833 ± 0.289 |
| M2 no-domain-adapter | 10.239 ± 0.278 | 10.169 ± 0.326 | 0.750 ± 0 | 0.667 ± 0.289 |
| M2 no-history | 11.756 ± 1.757 | 11.407 ± 1.736 | 0.861 ± 0.127 | 0.833 ± 0.289 |
| M2 SOH single-task | 11.552 ± 1.148 | 11.240 ± 1.186 | unsupported | unsupported |

M2 的 SOH 负迁移保留为实际结果，没有反复调参把它抹去。MATR final 仅六个条码，其中最差对象及逐对象误差完整记录，不能只挑正常表现对象。DyAD final 为 15 个独立车辆（14 正常、1 异常），每车预定首个 landmark 计算主 AUCPR；120 个片段的 AUCPR 另列，不能伪装为 120 个独立车辆。仅一个异常车辆使 AUCPR 非常不稳定，三种子均值不构成广泛部署证据。独立校准仅 10 车辆（9 正常、1 异常），Platt 为 `insufficient_calibration_class_objects`，无拟合系数与概率校准有效性声明。

MATR 80% object-max CQR 在六个独立校准对象上可产生有限区间；final 的 M1 landmark 覆盖率为 95.83%，整组轨迹覆盖率为 66.67%，平均宽度 13.419 ± 0.728 百分点。M2 joint 对应 100%、100%，但平均宽度 105.861 ± 25.972 百分点，显著过宽。覆盖率与宽度一起报告；不能仅凭 100% 覆盖声称校准或模型优秀。小数据的交换性条件与实际组内轨迹覆盖都保留限制。完整 dev/final 每域、每头、逐对象、删失/缺标签、指标不可用原因位于两个 summary 及每个 run 的 JSON。

## CH 公开生成故障独立基准

`generated_fault.py` / `scripts/v2/benchmark_generated.py` 使用真实下载的作者发布包，固定三种子、每化学体系 GBDT、train-only 预处理、独立 calibration 温度缩放和安全 JSON 数值树导出。其目标为 normal/high_resistance/low_capacity/self_discharge 四类别，始终为 `demo_synthetic/public_generated`，不混入 `experimental` 或本项目 LLM `expert_synthetic`。原生数值只形成统计特征，没有按虚构单位换算。原始母本 ID 未公开，48 个 VIN 只是保守根组；两个化学体系合并指标按 VIN 合并，不能把 96 条记录视作 96 个独立对象。

实际执行命令：

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
.venv/bin/python -m model_lab.scripts.v2.benchmark_generated \
--config model_lab/configs/generated_fault_v2.yaml --allow-exploratory-final
```

实际输出 `model_lab/reports/v2/ch_generated_20261002`：train/dev/calibration/final 为 29/7/5/7 个 VIN 根组（58/14/10/14 条记录），三个种子全部完成。每化学体系五个独立校准根组的类别数为 high_resistance 1、low_capacity 1、normal 2、self_discharge 1；温度拟合完成不等于在五个对象上已证明概率校准可靠。

| 范围 | dev 可评分类宏 AUPRC | 探索性 final 可评分类宏 AUPRC |
|---|---:|---:|
| LFP | 0.455 ± 0.014 | 0.964 ± 0.041 |
| NCM | 0.746 ± 0.010 | 0.852 ± 0.028 |
| 合并 VIN | 0.702 ± 0 | 0.938 ± 0.060 |

dev 缺 high_resistance，final 缺 normal，所以完整四分类宏 AUPRC 一律 `null`，表中仅为当时有可评正负样本类别的均值；两个 split 的数值不能当作同一完整四分类性能直接比较。母本独立性未知、样本极少，final 明确标为探索性，不证明真实车辆泛化。每种子 JSON 模型重载逐条重现全部保存的 train/dev/final VIN 预测与指标，最大绝对差为 0；`inference_validation.json` 同时记录 train/dev/calibration/final 根组隔离。10 个 CH 自动测试为构造夹具，实际数据检查和真实预测重放作为独立证据记录，不能混称成真实数据测试数量。

## 最终模块验收与提交边界

根 UV 的 scikit-learn 1.7.2 环境执行 `pytest model_lab/tests/v2 -q`：**35 passed in 2.25s**，覆盖数据/来源 13 项、特征 2 项、模型/遮罩/生存/校准 10 项、CH 构造夹具 10 项。随后新增 `prepare_official_subsets.py` 的四个轻量守卫测试单独 **4 passed in 0.04s**，不重复实际解析、训练和 final。它补齐实际 MATR 摘要/Arbin CSV、DyAD 安全转换、CH 原生 CSV 的可复现入口；原始路径/依赖与四条准确命令见 `sources/DELIVERY.md`。实际原始数据六个包的 hash/分组审计、30 个正式模型（另保留 15 个 superseded 开发 pilot）、CH 三种子实际训练和安全重载是单独的执行证据，不冒充自动测试数量。

四个提交的安全包为 `M1_joint_seed0_complete`、`M2_joint_seed0`、`M1_multisource_seed0`、`M2_multisource_seed0`。seed0 是固定展示约定，完整三种子结果仍全部报告。新增多源包的版本为 `multisource_fixed_loss_20261002:M1_joint_seed0` / `...:M2_joint_seed0`，避免与旧 XJTU 同名 run_id 混淆。包中的原始数值模型没有改动；仅将原 M1 保存样例的元数据更新为主 quantile/CQR 与独立 NGBoost alternative，并重新计算包回执 hash。不可变的训练记录仍保存训练时的代码/环境 hash。

下述重放已在根 UV 环境实际通过，完整回执为 `model_lab/reports/v2/package_replay_20261002.json`；所有保存 profile 的值与结构按 `1e-7` 容差匹配，真实 DyAD 输入仅 fault supported，真实 MATR/XJTU 输入仅 SOH supported，其他头均明确 unsupported。此命令只依赖提交的安全包和开发样例，不依赖本机绝对原始路径、最终数据或 pickle：

```bash
uv run python -m model_lab.scripts.v2.verify_package \
--package model_lab/reports/v2/packages/M1_joint_seed0_complete \
--package model_lab/reports/v2/packages/M2_joint_seed0 \
--package model_lab/reports/v2/packages/M1_multisource_seed0 \
--package model_lab/reports/v2/packages/M2_multisource_seed0
```

代码、配置、独立文档、小型官方 JSON/许可回执、各 run 参数与完整指标、四个安全包及 XJTU 18 对象的开发/校准特征包进入提交。原始数据 bulk、官网整页/整份脚本、完整作者源码、全部 final 特征、ignored 本机环境与历史未选用的重复包保持本地。对应精确 path 列表在最终 `COMMIT_MANIFEST.json`；父 Agent 在 DEV 分支按阶段 Commit，本子任务不自行 Commit。

## MATR 三批原始 MAT 的新增资格验收（进行中）

上述数值结果与子集接入已完成；实施方案 3.3 的完整 corrected 三批原始 MAT 续测身份验收尚未完成。根 Agent 继续授权按官方稳定 URL 受预算获取三批共约 8.269 GB 文件，通过 7897 代理、每文件上限 4 GiB、保持至少 70 GiB 磁盘余量，原始文件仍 ignored。下载成功后仅流式读取逐电芯身份/summary 和至多 32 个原始片段，不在 16 GB 内存上递归展开全部曲线；真实 barcode/连续性不足则记录明确失败。已有 45 个 run 和 MATR 摘要已消费的 final 完全不变；新原始域的资格审计与可能新增开发模型另行预登记。当前 `COMMIT_MANIFEST.json` 只列已稳定的数值/子集交付，不把尚未下载验收的原始 MAT 声称完成，也不以构造夹具证明真实续测身份。
