# 数据库迁移指南

## 概述
本文档提供了将现有数据库结构迁移到与FastAPI后端SQLAlchemy模型匹配的新结构的详细步骤。

## 当前系统架构对比

### 原始数据库结构 (database_schema.sql)
- 基于电池生命周期数据的专用数据库
- 包含电池基本信息、生命周期数据、模型信息等表
- 主要针对Severson电池数据集设计

### 新数据库结构 (backend_database_schema.sql)
- 基于用户认证和权限管理的通用数据库
- 包含用户、电池数据、模型、训练记录、预测记录、数据集、模型比较等表
- 支持多用户、权限控制和完整的机器学习工作流

## 迁移步骤

### 1. 备份现有数据
```bash
mysqldump -u username -p battery_soh_db > backup_battery_soh_db_$(date +%Y%m%d_%H%M%S).sql
```

### 2. 创建新的后端数据库
```sql
SOURCE backend_database_schema.sql;
```

### 3. 数据转换规则

#### 电池数据转换
- 从 `battery_lifecycle_data` 表提取数据
- 将 `battery_id` 映射到新表的 `battery_id` 字段
- 将 `voltage`, `current`, `temperature`, `capacity`, `resistance`, `soc`, `soh`, `power` 映射到相应字段
- 将 `rul` 和 `pcl` 分别作为预测目标保存
- 为每条记录分配给默认用户或根据需要分配给特定用户

#### 模型信息转换
- 从 `model_info` 和 `model_parameters` 表合并数据
- 将模型类型映射到新表的 `algorithm_type` 字段
- 将模型参数存储为JSON格式到 `hyperparameters` 字段
- 保留模型的性能指标到 `metrics` 字段

#### 训练记录转换
- 从 `training_records` 和 `training_epoch_details` 表合并数据
- 将训练配置信息存储为JSON格式
- 保留性能指标和训练统计信息

#### 预测结果转换
- 从 `prediction_results` 表提取数据
- 将预测结果按类型（SOH/RUL/PCL）分类
- 保留误差和置信度信息

### 4. 数据迁移脚本示例

```sql
-- 示例：迁移电池数据
INSERT INTO battery_soh_backend_db.battery_data (
    user_id, battery_id, capacity, voltage, temperature, 
    cycle_count, soc, soh, internal_resistance,
    charge_current, discharge_current, charge_voltage, 
    discharge_voltage, energy_efficiency, peak_power, 
    self_discharge_rate, timestamp, data_source
)
SELECT 
    1, -- 默认分配给用户ID 1
    blc.battery_id,
    blc.capacity,
    blc.voltage,
    blc.temperature,
    blc.cycle_count,
    blc.soc,
    blc.soh,
    blc.resistance AS internal_resistance,
    CASE WHEN blc.current > 0 THEN blc.current ELSE 0 END AS charge_current,
    CASE WHEN blc.current < 0 THEN ABS(blc.current) ELSE 0 END AS discharge_current,
    NULL AS charge_voltage,
    NULL AS discharge_voltage,
    NULL AS energy_efficiency,
    blc.power AS peak_power,
    NULL AS self_discharge_rate,
    blc.test_timestamp AS timestamp,
    'migrated' AS data_source
FROM battery_soh_db.battery_lifecycle_data blc;

-- 示例：迁移模型数据
INSERT INTO battery_soh_backend_db.models (
    user_id, name, algorithm_type, framework, description,
    hyperparameters, metrics, status, is_active
)
SELECT 
    1, -- 默认分配给用户ID 1
    mi.model_name,
    mi.model_type AS algorithm_type,
    'PyTorch' AS framework,
    mi.description,
    mp.extra_params AS hyperparameters,
    CONCAT('{"train_loss": ', COALESCE(tr.final_train_loss, 'null'), 
           ', "val_loss": ', COALESCE(tr.final_val_loss, 'null'), '}') AS metrics,
    mi.status,
    CASE WHEN mi.status = 'deployed' THEN 1 ELSE 0 END AS is_active
FROM battery_soh_db.model_info mi
LEFT JOIN battery_soh_db.model_parameters mp ON mi.model_id = mp.model_id
LEFT JOIN battery_soh_db.training_records tr ON mi.model_id = tr.model_id;
```

### 5. 验证迁移结果

运行以下查询验证数据迁移：

```sql
-- 验证用户表
SELECT COUNT(*) AS user_count FROM battery_soh_backend_db.users;

-- 验证电池数据
SELECT COUNT(*) AS battery_data_count FROM battery_soh_backend_db.battery_data;

-- 验证模型数据
SELECT COUNT(*) AS model_count FROM battery_soh_backend_db.models;

-- 验证训练记录
SELECT COUNT(*) AS training_count FROM battery_soh_backend_db.training_records;

-- 验证预测记录
SELECT COUNT(*) AS prediction_count FROM battery_soh_backend_db.prediction_records;
```

## 新功能说明

### 1. 用户管理系统
- 支持用户注册、登录和身份验证
- 角色管理（普通用户、管理员）
- 权限控制

### 2. 完整的ML工作流
- 数据集管理
- 模型训练跟踪
- 预测结果记录
- 模型比较功能

### 3. 扩展的电池数据字段
- 更多电池特性参数
- 支持充电/放电参数
- 效率和功率参数

## 注意事项

1. **数据丢失风险**: 迁移过程中可能会丢失一些无法直接映射的数据
2. **外键约束**: 新结构中的外键约束可能需要调整迁移顺序
3. **数据类型转换**: 某些字段的数据类型可能需要转换
4. **索引重建**: 迁移后建议重新评估和创建适当的索引

## 回滚计划

如果迁移出现问题：
1. 使用备份恢复原始数据库
2. 删除新的后端数据库
3. 重新评估迁移策略

## 后续步骤

1. 部署视图和存储过程
2. 配置应用程序连接新数据库
3. 测试所有功能
4. 监控性能