# V2 numerical/data implementation record

Date: 2026-10-02 (Asia/Shanghai). This is an additive `model_lab` V2 research namespace. V1 models, artifacts, splits, and the three protected XJTU `*-5` cells remain untouched. No protected cell was opened, hashed, transformed, trained on, calibrated, or scored.

## Data and provenance

`model_lab/modeling/v2/data.py` provides source-preserving contracts and guarded MATLAB/HDF5/CSV/Parquet readers. Pickle/joblib loading is rejected, HDF5 links are rejected, raw files are hash recorded, and every exclusion is persisted. XJTU cycles preserve source ordinal and set `physical_cycles_known=false`; this prevents an ordinal from silently becoming a RUL cycle. Measured XJTU SOH targets use a frozen first observed diagnostic reference. RUL, efficiency, and fault labels remain unavailable unless a source supplies verified physical time/threshold, complete metering boundaries, or confirmed root-cause labels.

`model_lab/modeling/v2/sources.py` and `scripts/v2/ingest.py` maintain a YAML registry with official landing/resolved links, retrieval time, license status, bytes, author checksum and SHA-256. Retrieval uses `http://127.0.0.1:7897`. All four sources now have actual parsed data with explicitly limited `raw_scope`: XJTU measured RPT/curves; three corrected MATR MATLAB batches, one complete MATR Arbin cell and official 2018 capacity-summary measurements; DyAD brand-3 vehicle snippets; CH public generated fault data. Detailed counts, exclusions, actual download attempts, license receipts, and commands are in `model_lab/reports/v2/sources/DELIVERY.md`. Full raw downloads and full official HTML/JavaScript stay local; small official JSON, license summaries, URLs and hash receipts enter version control. XJTU, MATR and DyAD retain observed CC BY 4.0 metadata; CH retains CC BY-NC-SA 4.0 and the provider's academic/non-commercial/additional redistribution terms. CH raw data is not uploaded.

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

The supported experimental heads are measured XJTU SOH, MATR capacity-reference SOH, and DyAD retrospective vehicle-anomaly classification. DyAD chemistry remains `unknown`, its native channel units are unverified, and its local timestamp is not promoted to a global clock. These data do not establish cell root-cause classification. RUL/efficiency/fault support remains unavailable on XJTU; MATR summary ordinal cannot provide physical-cycle RUL. The single complete MATR Arbin cell does have 542 explicit `Cycle_Index` cycles and a genuine 0.88 Ah event/censoring target, but one cell does not establish independently validated deployable lifetime prediction. The later corrected MATLAB qualification recovers the author-selected 124-object data view; the published feature/model/performance benchmark is not claimed as reproduced. The earlier summary-only `paper_reproduction.json` is a frozen historical block, superseded for data qualification by `corrected_parse_qualification.json`. Efficiency requires complete metering/SOC boundaries; no current fitted package claims it. Such outputs remain unsupported and cannot feed carbon accounting as validated lifetime/efficiency parameters.

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

## 首次数值 checkpoint 验收与提交边界

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

## MATR 三批原始 MAT 的实际资格验收

实施方案 3.3 的 corrected MAT 三批已完成真实下载与资格验收。三文件合计 **8,269,341,808 bytes**，官方大小匹配并记录本地 SHA256；没有作者公布摘要，故不冒称作者校验。网络通过 7897、最多两文件并发、每文件 4 GiB、磁盘至少保留 70 GiB；原始文件只读且 ignored。详情与准确重放命令在 `sources/DELIVERY.md`。

新 `matr_stream.py` 按逐电芯 HDF5 引用流式读取，以限定 MATLAB MCOS 字符串表还原 barcode/channel，不执行 MATLAB 类、不递归展开 8 GB 全曲线。**140 原始 struct 的 barcode 与原生 channel 均逐一通过三批官方 tests API 核对，5 对真实续测验证身份和测量连续性，合并为 135 独立物理电芯**。身份-only inventory 在数值目标读取前冻结 81 train / 27 dev / 27 calibration / 0 final。实际 source audit 通过，134 个有测量对象、113,303 周期、4,241 原始片段、112,143 SOH 标签。

按作者 `LoadData.m` 的真实顺序过滤和过滤后的索引规则得到 B1 41 / B2 43 / B3 40，共 **124** 个论文数据视图对象，11 个排除逐条记录；没有硬凑 124 或以构造的 T01 替代原始条码。物理 0.88 Ah **严格小于**阈值下真实为 **43 exact / 91 right-censored**，末次循环加一仅为单独命名的作者输出约定，绝不成为物理死亡事件。周期 10 原始曲线支持 134 对象，周期 100 支持 133，对缺失/不合法原始曲线不补造。此交付完成数据资格与作者选择视图，不宣称已经重现论文的 ΔQ100−10 特征、论文预测器或发表指标。

`corrected_identity_qualification.json`、`corrected_parse_qualification.json`、三个下载回执和 `matr_corrected_data_receipt.json` 保存真实 hash、数量、身份与续测证据。已有 XJTU/MATR/DyAD final、旧 run、容量图的冻结历史记录不改写、不重评。

## MATR 固定物理前缀的生命周期开发协议

新增 `lifetime_features.py` 与独立 `MATR_LIFETIME_PROTOCOL.md`。query 在首次 fit 前固定为 **50 / 100 / 200 物理循环**，输入严格早于 query，容量参考固定为已经可见的首个 cycle≥10 有效容量。精确/区间/右删失绝对边界减 query 得剩余物理循环；已死亡、区间跨 query 或未观察到 query 的对象/窗口排除。未来生命周期、终点容量与标签可用时刻不在输入投影列中。所有原始充电 policy 保持精确域键，不为增加样本池化；5 个真续测对象的 policy 改变，因此整个对象在本次固定 policy 模型中排除，完整资格源仍保留。

六个此前 MATR 容量摘要 final barcode 从其 JSON 身份元数据提取，NPZ 未打开，在 Parquet 数值列投影前排除。后端 reader 的共享 row-group 内部扫描不冒称字节级隔离。旧 train/dev/calibration 条码仍与本次来源重叠，所以这不是干净独立来源泛化实验。实际建成 **123 对象、368 query rows：79 train / 23 dev / 21 calibration / 0 final，240 right / 128 exact / 0 interval rows**。排除还包括一条原始采集问题和一个 query 事件已发生，原因和不同分母完整保存。

初始 32历史×256点输入包已构造但从未 fit；因 16 GB 机器上的整个 15-run 矩阵计算预算，在读取 dev 成绩前新建 8历史×64点包并冻结配置，query、可见规则、宽度128/adapter32不变，全部模型/消融使用同一预算输入。两个 feature receipt 保存这一先后顺序。68 个精确 policy 仅17个有至少两个独立 train 生存对象；2对象只是最低研究拟合守卫，绝非部署验证样本量。低样本 policy 的 RUL/risk 为 unsupported，缺效率与故障标签仍保持缺失。

## Phase 17：真实删失 M1/M2、遮罩修复与最终提交记录

新增配置 `model_v2_matr_lifetime_masked.yaml` 首次 fit 前冻结 M1 joint×3、M2 joint/no-domain-adapter/no-history/SOH single-task×3，共15次。M2三种联合版本的真实训练 history 每轮明确激活 `rul` 与 `soh`；single-task只有SOH。独立calibration与dev评估均成功，所有run的参数/hash/训练损失/支持矩阵/逐对象与逐域指标完整保留。`reports/v2/matr_lifetime_development_masked_20261002/BENCHMARK.md` 列全部共同策略域的三种子SOH与删失NLL，并保留负结果。

六个共同可评 RUL 策略域有8个独立dev对象（1 exact/7 right）。普通 `4.8C(80%)-4.8C` 域单个事件对象，M1 NLL 2.378169±0，M2 joint 0.968311±0.077945；其他五域全部右删失，接近零的M1 NLL只说明概率置于观察窗之后，不能证明未知真实寿命正确。M2 no-adapter/no-history的所有域结果一并报告。全部合法域的C-index为null，因为没有跨对象、同query起点、已知可排序事件边界的合法对。known-status Brier按对象平均，保留每H可知状态对象数，不冒称IPCW或已校准概率。

精确policy校准域最多2对象，α0.2的80% object-max CQR全部无界/样本不足。寿命生存函数与风险1−S(H)来自同一hazard，`calibration_version=null`；没有寿命概率校准成功声明。效率和故障仍因实际来源无合法标签unsupported。M1与M2的两对象门槛只用于最低研究拟合，不作为部署门槛。

第一轮实际15次生命周期开发诊断 `matr_lifetime_development_20261002` 发现离线 `MultiTaskModel.predict` 对未知dev/calibration-only policy回退全局标签支持的问题。原安全package query gate当时已拒绝未知policy，但离线metrics/CQR也必须遮罩。修为未知policy全头NaN，并扩展既有守卫测试；旧run/原结果不覆盖，`diagnostic_status.json`标记superseded_before_final。纠正版仅修适用性遮罩，所有配置/种子/输入完全一致，未用开发分数改参数。诊断导出包与未完成旧M1副本移动到ignored研究缓存，移动前后hash/路径在 `sources/local_cache_relocation_20261002.json`；没有删除原始数据或改写历史hash锁回执。

旧摘要和本次有29个非final条码重叠：旧train17→新train；旧dev5→新train、旧dev1→新dev；旧calibration6→新dev。旧final交集0。`overlap_receipt.json`明确暴露历史，不将新开发成绩叫独立来源泛化。

新增安全JSON/NPZ包为 `M1_matr_lifetime_masked_seed0` 与 `M2_matr_lifetime_masked_seed0`，版本含完整实验名，原四包不覆盖。种子0是固定展示约定；未按性能选择种子。新包各21个真实dev输入/20域，既含supported也含unsupported，输入仅数值特征/曲线/mask/domain和合法query，剔除未来label时刻与删失状态。所有新profile记录 `evidence_status=development_only_research`、`validated_deployment=false`，不得自动作为Carbon已验证参数。原四包加新两包整体profile重放均通过1e-7，回执 `package_replay_with_lifetime_units_20261002.json`。

实际交付还包含预算开发特征 `data/derived/v2/matr_lifetime_development_20261002_budgeted/features.json`（1,081,151 bytes）与 `features.npz`（818,798 bytes），123 train/dev/cal对象、0 final、无保护XJTU，array路径相对。它允许fresh clone研究复训；原8GB、全部final数值及未训练32×256大包不提交。MATR实测数据许可来源和引用由来源回执保留。

安全数值模型新 `safe_numeric.py` 严格拒绝JSON布尔/数值字符串/非有限值作为数值、树循环或共享父节点、错误shape/index、异常NGBoost维度/scale、survival参数/预算等。47项严格模型JSON测试与13项模型集成共60通过；未知policy修复后同13模型测试再通过1.73s。来源stream+CLI15项、生命周期fixture5项分别通过。它们是软件夹具测试，真实140身份/续测审计、真实30新增生命周期训练（15诊断+15正式开发）和包重放是独立执行证据。最终根全仓测试另由主Agent记录，不把历史35项说成新增后的全量结果。

准确新训练/校准/评估/来源重放命令见新BENCHMARK和来源DELIVERY。输出/校准不可覆盖；实际复现必须使用新output名称，development_only配置拒绝final即便提供authorize-final。所有本次新增/改动、每run完整参数与结果、安全包和强制加入NPZ列表精确登记在 `reports/v2/MATR_FOLLOWUP_COMMIT_MANIFEST.json`；父Agent在DEV执行Phase17 Commit，本模块不自行提交。

Phase17 最终元数据复核将 threshold_risk 的 unit 从继承的 physical_cycle 改为 probability；风险 H 仍按物理循环、RUL unit 仍 physical_cycle。只修两份新增研究包的保存profile及相应hash，逐项归一化比较证明全部数值不变，原四包与训练/指标不改。unit_metadata_correction.json 保留修正前后模型和manifest hash；修正后六包再次完整1e-7重放通过。先前回执保留为修正前历史记录，最新回执使用 units 后缀。
