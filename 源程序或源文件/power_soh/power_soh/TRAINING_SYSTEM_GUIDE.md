# 训练系统完善指南

## 概述

训练系统已经完善，现在模型应该从**算法训练平台**训练后自动生成，而不是手动插入到数据库。

## 已完成的功能

### 1. 后端训练API (`backend/api/training.py`)

- ✅ **创建训练任务** (`POST /api/training`)
  - 接收训练参数（算法类型、电池组ID、网络参数、超参数等）
  - 创建模型记录和训练记录
  - 在后台异步执行训练任务

- ✅ **获取训练任务列表** (`GET /api/training`)
  - 返回用户的所有训练任务

- ✅ **获取训练任务详情** (`GET /api/training/{task_id}`)
  - 返回训练任务的详细信息和日志

- ✅ **停止训练任务** (`PUT /api/training/{task_id}`)
  - 支持停止正在运行的训练任务

- ✅ **训练执行逻辑** (`execute_training`)
  - 支持三种算法：Baseline、BiLSTM、DeepHPM
  - 从数据库加载电池数据
  - 执行真正的模型训练
  - 保存训练好的模型文件到 `results/` 目录
  - 将模型信息保存到数据库的 `models` 表
  - 记录训练日志和评估指标

### 2. 前端训练平台 (`frontend/src/views/TrainPlatform.vue`)

- ✅ **训练功能**
  - 调用后端API创建训练任务
  - 实时轮询训练进度（每2秒）
  - 显示训练日志和损失曲线
  - 支持停止训练

- ✅ **训练参数配置**
  - 算法选择（Baseline、BiLSTM、DeepHPM）
  - 网络结构参数（层数、节点数、激活函数）
  - 训练超参数（学习率、批大小、迭代次数、优化器）
  - 数据集划分（训练集比例）

### 3. 测试平台模型加载 (`frontend/src/views/TestPlatform.vue`)

- ✅ **模型列表加载**
  - 从数据库的 `models` 表获取模型列表
  - 显示所有已训练完成的模型
  - 支持按算法类型筛选

## 使用流程

### 1. 训练模型

1. 打开**算法训练平台**
2. 选择算法类型（Baseline/BiLSTM/DeepHPM）
3. 配置网络结构参数和超参数
4. 选择用于训练的电池组
5. 点击**开始训练**按钮
6. 系统会在后台执行训练，实时显示进度
7. 训练完成后，模型自动保存到：
   - 模型文件：`results/SoH_{algorithm}_{timestamp}.pth`
   - 数据库记录：`models` 表

### 2. 使用训练好的模型进行预测

1. 打开**算法测试平台**
2. 在"选择已训练好的预测算法模型"下拉框中选择模型
3. 选择待预测的电池组
4. 配置预测参数
5. 点击**开始预测**

## 删除测试数据

如果之前手动插入了测试模型数据，可以使用以下SQL脚本删除：

```bash
# 方式1：使用SQL脚本
mysql -u root -p battery_soh_db < delete_test_models.sql

# 方式2：直接执行SQL
DELETE FROM models 
WHERE name IN (
    'Baseline_SoH_CaseA',
    'BiLSTM_SoH_CaseA',
    'DeepHPM_SoH_CaseA'
)
AND algorithm_type IN ('baseline', 'bilstm', 'deepphm');
```

## 注意事项

### 1. 数据文件要求

- 训练需要 `SeversonBattery.mat` 文件位于项目根目录
- 如果文件不存在，训练会失败并记录错误日志

### 2. 训练时间

- 训练是异步执行的，在后台运行
- 训练时间取决于：
  - 选择的电池组数量
  - 训练轮数（epochs）
  - 计算机性能（CPU/GPU）

### 3. 模型文件存储

- 训练好的模型文件保存在 `results/` 目录
- 模型文件名格式：`SoH_{algorithm_type}_{timestamp}.pth`
- 模型信息（路径、大小、指标等）保存在数据库

### 4. 训练状态

- `training`: 正在训练中
- `completed`: 训练完成
- `failed`: 训练失败
- `stopped`: 训练已停止

### 5. 数据库记录

每个训练任务会创建两条记录：
- **models表**：模型信息（算法、参数、指标、文件路径等）
- **training_records表**：训练记录（配置、日志、状态等）

## API接口说明

### 创建训练任务

```http
POST /api/training
Content-Type: application/json
Authorization: Bearer {token}

{
  "algorithm_type": "baseline",
  "battery_ids": [91, 100, 124],
  "network_params": {
    "layers": 2,
    "nodes": 64,
    "activation": "tanh"
  },
  "hyperparams": {
    "learning_rate": 0.001,
    "batch_size": 32,
    "epochs": 100,
    "optimizer": "adam"
  },
  "dataset_split": {
    "train_ratio": 0.8,
    "validation_ratio": 0.2
  }
}
```

### 响应

```json
{
  "success": true,
  "message": "训练任务已创建，正在后台执行",
  "data": {
    "model_id": 1,
    "training_record_id": 1,
    "model_name": "BASELINE_20231215_143022",
    "status": "training"
  }
}
```

## 故障排查

### 问题1：训练任务创建失败

**原因**：
- 未选择电池组
- 电池组不存在
- 数据库连接失败

**解决方案**：
- 确保至少选择了一个电池组
- 检查电池组是否存在于数据库中
- 检查数据库连接配置

### 问题2：训练失败

**原因**：
- 数据文件不存在
- 内存不足
- 依赖包缺失

**解决方案**：
- 确保 `SeversonBattery.mat` 文件存在
- 检查系统资源
- 安装所有依赖包（PyTorch、scipy、numpy等）

### 问题3：模型列表为空

**原因**：
- 还没有训练过模型
- 模型状态不是 `completed`

**解决方案**：
- 先在训练平台训练模型
- 检查模型的 `status` 字段是否为 `completed`
- 确保模型的 `is_active` 字段为 `true`

## 下一步改进建议

1. **实时训练进度推送**
   - 使用WebSocket实现实时训练进度推送
   - 替代轮询机制，提高效率

2. **训练任务管理**
   - 支持查看历史训练任务
   - 支持重新训练
   - 支持导出训练报告

3. **模型版本管理**
   - 支持模型版本控制
   - 支持模型回滚

4. **性能优化**
   - 支持GPU加速训练
   - 支持分布式训练
   - 优化大数据量处理
