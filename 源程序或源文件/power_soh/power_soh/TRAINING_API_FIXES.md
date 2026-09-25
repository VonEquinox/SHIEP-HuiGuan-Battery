# 训练API修复说明

## 修复的问题

### 1. CORS错误
**问题**: 前端请求后端API时被CORS策略阻止
**原因**: CORS配置已正确，但可能需要确保后端服务器正在运行
**解决方案**: 
- CORS配置已在`backend/main.py`中正确设置
- 确保后端服务器正在运行在正确的端口（默认5000）
- 确保前端请求的URL正确（`http://localhost:5000/api/training`）

### 2. 500内部服务器错误
**问题**: 后端API处理训练记录详情时出错
**原因**: 
- 字段名称错误：使用了`training_logs`而实际字段是`logs`
- 字段名称错误：使用了`completed_at`而实际字段是`end_time`

**修复**:
- ✅ 修复了所有`training_logs`引用为`logs`
- ✅ 修复了所有`completed_at`引用为`end_time`
- ✅ 修复了训练记录查询和返回的数据结构

### 3. 训练逻辑不完善
**问题**: 训练API中的模型训练逻辑与实际的三个训练脚本不一致
**原因**: 
- Baseline、BiLSTM、DeepHPM三个算法的实现需要根据实际的训练脚本完善

**修复**:
- ✅ **Baseline算法**: 使用`func.DataDrivenNN`模型，使用`func.My_loss(mode='Baseline')`损失函数
- ✅ **BiLSTM算法**: 使用自定义`BiLSTMModel`，使用`MSELoss`损失函数，禁用cuDNN
- ✅ **DeepHPM算法**: 使用`func.DeepHPMNN`模型，使用`func.My_loss(mode='Sum')`损失函数，禁用cuDNN
- ✅ **训练循环**: Baseline和DeepHPM使用`func.train`函数，BiLSTM使用标准训练循环
- ✅ **学习率调度器**: 所有算法都使用`StepLR`调度器

### 4. 评估指标计算不正确
**问题**: 评估指标（RMSPE、MSE、MAE、R²）的计算方式与训练脚本不一致
**原因**: 简化了评估指标的计算，没有按照训练脚本的方式计算

**修复**:
- ✅ **SoH转换**: 所有预测结果都需要从容量损失（PCL）转换为健康状态（SoH）：`SoH = 1 - PCL`
- ✅ **RMSPE计算**: 使用正确的公式：`sqrt(mean(((pred - actual) / actual) ^ 2))`
- ✅ **MSE计算**: 使用正确的公式：`mean((pred - actual) ^ 2)`
- ✅ **MAE计算**: 使用正确的公式：`mean(abs(pred - actual))`
- ✅ **R²计算**: 使用正确的公式：`1 - (SS_res / SS_tot)`
- ✅ **训练集和验证集指标**: 分别计算训练集和验证集的指标

### 5. 数据库字段映射错误
**问题**: 训练记录的字段与数据库模型不匹配
**原因**: 使用了错误的字段名称

**修复**:
- ✅ `training_logs` -> `logs`
- ✅ `completed_at` -> `end_time`
- ✅ 添加了`duration`、`final_loss`、`best_val_loss`等字段的更新
- ✅ 添加了`train_metrics`和`validation_metrics`的保存

## 训练流程说明

### 1. Baseline算法训练流程
```
1. 加载数据 -> SeversonBattery
2. 数据分割 -> create_chosen_cells
3. 标准化 -> standardize_tensor
4. 构建模型 -> DataDrivenNN (使用layers参数)
5. 设置损失函数 -> My_loss(mode='Baseline')
6. 设置优化器 -> Adam
7. 设置调度器 -> StepLR
8. 训练 -> func.train
9. 评估 -> 计算RMSPE、MSE、MAE、R²
10. 保存模型 -> torch.save
```

### 2. BiLSTM算法训练流程
```
1. 加载数据 -> SeversonBattery
2. 数据分割 -> create_chosen_cells
3. 标准化 -> standardize_tensor
4. 构建模型 -> BiLSTMModel (双向LSTM + 全连接层)
5. 禁用cuDNN -> torch.backends.cudnn.enabled = False
6. 设置损失函数 -> MSELoss
7. 设置优化器 -> Adam
8. 设置调度器 -> StepLR
9. 训练 -> 标准训练循环
10. 评估 -> 计算RMSPE、MSE、MAE、R²
11. 保存模型 -> torch.save
```

### 3. DeepHPM算法训练流程
```
1. 加载数据 -> SeversonBattery
2. 数据分割 -> create_chosen_cells
3. 标准化 -> standardize_tensor
4. 构建模型 -> DeepHPMNN (使用layers和inputs_dynamical参数)
5. 禁用cuDNN -> torch.backends.cudnn.enabled = False
6. 设置损失函数 -> My_loss(mode='Sum') (数据拟合 + 物理约束 + 时间导数)
7. 设置优化器 -> Adam
8. 设置调度器 -> StepLR
9. 训练 -> func.train
10. 评估 -> 计算RMSPE、MSE、MAE、R²
11. 保存模型 -> torch.save
```

## API使用示例

### 创建训练任务

```http
POST /api/training
Content-Type: application/json
Authorization: Bearer {token}

{
  "algorithm_type": "baseline",
  "battery_ids": [91, 100],
  "network_params": {
    "layers": 2,
    "nodes": 64,
    "activation": "tanh"
  },
  "hyperparams": {
    "learning_rate": 0.001,
    "batch_size": 32,
    "epochs": 100,
    "optimizer": "adam",
    "step_size": 30,
    "gamma": 0.1
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

### 获取训练任务详情

```http
GET /api/training/{task_id}
Authorization: Bearer {token}
```

### 响应

```json
{
  "id": 1,
  "model_id": 1,
  "model_name": "BASELINE_20231215_143022",
  "status": "completed",
  "training_logs": "...",
  "train_metrics": {
    "rmspe": 0.0234,
    "mse": 0.0005,
    "mae": 0.0187,
    "r2": 0.9786
  },
  "validation_metrics": {
    "rmspe": 0.0256,
    "mse": 0.0006,
    "mae": 0.0198,
    "r2": 0.9712
  }
}
```

## 注意事项

1. **数据文件要求**: 训练需要`SeversonBattery.mat`文件位于项目根目录
2. **训练时间**: 训练是异步执行的，在后台运行，可能需要较长时间
3. **模型文件**: 训练完成后，模型文件保存在`results/`目录
4. **数据库记录**: 训练完成后，模型信息和训练记录保存在数据库中
5. **错误处理**: 如果训练失败，错误信息会记录在训练日志中，状态会更新为`failed`

## 测试建议

1. **测试Baseline算法**:
   - 选择2-3个电池组
   - 设置较少的epochs（如10-20轮）进行快速测试
   - 检查训练日志和评估指标

2. **测试BiLSTM算法**:
   - 选择2-3个电池组
   - 设置较少的epochs（如10-20轮）进行快速测试
   - 检查训练日志和评估指标

3. **测试DeepHPM算法**:
   - 选择2-3个电池组
   - 设置较少的epochs（如10-20轮）进行快速测试
   - 检查训练日志和评估指标

4. **检查数据库**:
   - 确认模型记录已创建
   - 确认训练记录已创建
   - 确认评估指标已保存

5. **检查模型文件**:
   - 确认模型文件已保存到`results/`目录
   - 确认模型文件大小合理
   - 确认可以加载模型文件

## 下一步改进建议

1. **实时进度推送**: 使用WebSocket实现实时训练进度推送，替代轮询机制
2. **训练任务管理**: 支持查看历史训练任务、重新训练、导出训练报告
3. **模型版本管理**: 支持模型版本控制、模型回滚
4. **性能优化**: 支持GPU加速训练、分布式训练、优化大数据量处理
5. **测试集评估**: 添加测试集评估功能，计算测试集指标
