# Battery model lab

## 当前已验收状态（2026-09-25）

XJTU 原始压缩包已完整下载并通过官方 MD5，已安全解压：55 个电芯 MAT 文件，以及 1 个温度补偿 MAT 文件。已实际读取一个原始电芯并核对字段结构；原始数据到模型输入的完整转换尚未完成。

已使用作者公开的 5 个派生特征电芯完成真实开发训练，按电芯 3/1/1 划分。首轮 3 epochs 在 Codex 环境内使用 CPU；主助手修复训练问题后又在主机 MPS 上完成 30 epochs、1 seed 的对照。15 项单元测试通过，逐样本指标已独立重算，CADA 最佳权重已在 CPU 重新加载验证。

**这不是正式模型效果验收。** 派生容量标签的逐点实测/插值来源未核实；仅 1 个验证电芯；测试电芯未评估；候选 CADA-v0 没有超过当前最好的普通 MLP。详细结果与后续任务见 `docs/HOST_REVIEW.md`、`reports/progress.json` 和 `reports/host_verification.json`。

This directory contains the auditable data and environment work for the battery-model stage. It is deliberately isolated from the existing application source, SQL, requirements documents, and existing weights.

## Scope for this stage

- Establish a reproducible Python environment and record exact package versions.
- Register public battery sources and their evidence, licenses, versions, and checksums.
- Download and validate a bounded XJTU sample/package when the official record permits it.
- Preserve raw files and derived manifests separately. Never overwrite a raw source in place.
- Parse only enough source structure to identify physical cells, cycles, fields, units, and labels without guessing SOH/PCL/RUL semantics.
- Freeze a cell-level 60/20/20 candidate split with identity mappings. The split is a candidate for review by the next model stage.

## Layout

```text
model_lab/
  data/raw/       downloaded source files (ignored by git)
  data/derived/   manifests, metadata, and parsed summaries
  docs/           user requirements and development log
  locks/          environment lock/export files
  scripts/        download, validate, and parse CLIs
  tests/          deterministic synthetic fixtures and tests
```

## Commands

```bash
uv venv --python 3.12 model_lab/.venv
uv pip install --python model_lab/.venv/bin/python -r model_lab/requirements.txt
model_lab/.venv/bin/python model_lab/scripts/data_cli.py registry
model_lab/.venv/bin/python model_lab/scripts/data_cli.py metadata xjtu
model_lab/.venv/bin/python model_lab/scripts/data_cli.py download xjtu
model_lab/.venv/bin/python model_lab/scripts/data_cli.py inspect xjtu
model_lab/.venv/bin/python -m pytest -q model_lab/tests
```

`download` is resumable and checksum-aware. It refuses unsafe archive members before extraction, estimates expansion size, and keeps a structured event log in `data/derived/download_events.jsonl`. No source-controlled file contains credentials or machine secrets.

## Data policy

The registry distinguishes `complete`, `partial`, and `blocked`; unavailable sources are not represented as usable samples. Physical-cell identity is preserved through every derived record. Training statistics must be fitted on the training-cell partition only. Synthetic fixtures, if used by tests, are labelled synthetic and cannot enter a training manifest.

## Training reproduction

```bash
model_lab/.venv/bin/python model_lab/scripts/train_soh.py \
  --data-glob 'model_lab/data/derived/author/PINN4SOH/xjtu/*.csv' \
  --out model_lab/reports/new_dev_run \
  --epochs 30 --seeds 0 --standardize-target
```

Choose a fresh `--out` directory for each run so verified evidence is not overwritten. Neural checkpoints, classical model files, input scaling, source/code hashes, epoch logs, and predictions must be kept together. Only load model files generated and trusted by this project; joblib/pickle files from untrusted sources must not be loaded.

This stage claims bounded real-data development execution only, not verified primary SOH accuracy, valid RUL prediction, global architectural novelty, or state-of-the-art results. HUST/MATR acquisition, raw-curve model training, multi-seed/group evaluation, and ablations remain unstarted.
