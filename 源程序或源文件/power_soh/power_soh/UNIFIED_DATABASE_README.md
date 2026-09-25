# 统一数据库架构说明文档

## 概述

本数据库架构专为储能电池寿命预测系统设计，基于 **SeversonBattery.mat** 数据文件，存储124组电池的完整生命周期数据。

## 主要特点

1. **简化用户管理**：移除了管理员角色，所有用户平等使用系统
2. **统一数据源**：所有电池数据来自 SeversonBattery.mat 文件
3. **完整生命周期数据**：包含8项特征数据、循环次数、RUL、PCL等

## 数据库结构

### 核心表

#### 1. `users` - 用户表
- 简化版用户表，移除了 `role` 字段（管理员功能）
- 保留基本用户信息：用户名、邮箱、密码、状态

#### 2. `battery_info` - 电池基本信息表
- 存储124组电池的基本信息
- 包含数据集类型划分（train/validation/test）
- 电池编号：1-124

#### 3. `battery_lifecycle_data` - 电池生命周期数据表
- **8项特征数据**（来自 Features_mov_Flt）：
  - voltage (电压)
  - current (电流)
  - temperature (温度)
  - capacity (容量)
  - resistance (内阻)
  - soc (荷电状态)
  - soh (健康状态)
  - power (功率)
- **预测目标**（来自 SeversonBattery.mat）：
  - cycle_count (循环次数)
  - rul (剩余使用寿命)
  - pcl (容量衰减百分比)

#### 4. `models` - 模型表
- 用户创建的机器学习模型
- 关联到用户ID

#### 5. `training_records` - 训练记录表
- 模型训练历史记录
- 包含训练指标和性能数据

#### 6. `prediction_records` - 预测记录表
- 模型预测结果记录
- 关联电池ID、模型ID和用户ID

#### 7. `datasets` - 数据集表
- 用户上传的数据集信息
- 注意：系统主要使用 SeversonBattery.mat 作为数据源

#### 8. `model_comparisons` - 模型比较表
- 模型性能比较结果

#### 9. `data_statistics` - 数据统计表
- 每个电池的统计信息
- 通过存储过程自动更新

## 文件说明

### 1. `unified_database_schema.sql`
- 主数据库架构文件
- 包含所有表的创建语句
- 初始化124组电池的基本信息

### 2. `unified_stored_procedures.sql`
- 数据库存储过程
- 包括：
  - `update_battery_statistics`: 更新电池统计信息
  - `update_user_activity_stats`: 更新用户活动统计
  - `get_model_performance_report`: 获取模型性能报告
  - `cleanup_old_data`: 清理旧数据
  - `get_system_health_report`: 系统健康报告
  - `check_data_consistency`: 数据一致性检查

### 3. `unified_views.sql`
- 数据库视图
- 包括：
  - `v_user_activity_overview`: 用户活动概览
  - `v_model_performance_overview`: 模型性能概览
  - `v_training_detailed`: 训练记录详情
  - `v_prediction_detailed`: 预测记录详情
  - `v_dataset_usage`: 数据集使用情况
  - `v_battery_data_stats`: 电池数据统计
  - `v_battery_overview`: 电池综合信息
  - `v_system_stats`: 系统整体统计

## 安装步骤

### 1. 创建数据库架构
```bash
mysql -u root -p < unified_database_schema.sql
```

### 2. 创建存储过程
```bash
mysql -u root -p battery_soh_db < unified_stored_procedures.sql
```

### 3. 创建视图
```bash
mysql -u root -p battery_soh_db < unified_views.sql
```

### 4. 导入电池数据
使用 `import_data_to_mysql.py` 脚本导入 SeversonBattery.mat 数据：
```bash
python import_data_to_mysql.py
```

## 数据导入

系统使用 `import_data_to_mysql.py` 脚本从 SeversonBattery.mat 文件导入数据：

1. 脚本会自动解析 MAT 文件中的：
   - `Features_mov_Flt`: 8项特征数据
   - `RUL_Flt`: 剩余使用寿命
   - `PCL_Flt`: 容量衰减百分比
   - `Cycles_Flt`: 循环次数
   - `Num_Cycles_Flt`: 每个电池的总循环数

2. 数据会自动分配到对应的电池ID（1-124）

3. 导入后会自动更新统计信息

## 主要修改

### 移除的功能
- ❌ 管理员角色（`role` 字段）
- ❌ 管理员专用存储过程
- ❌ 管理员权限检查

### 保留的功能
- ✅ 用户注册和登录
- ✅ 电池数据管理（基于 SeversonBattery.mat）
- ✅ 模型训练和预测
- ✅ 数据统计和分析
- ✅ 所有用户功能

## 数据关系

```
users
  ├── models (用户创建的模型)
  ├── training_records (训练记录)
  ├── prediction_records (预测记录)
  ├── datasets (数据集)
  └── model_comparisons (模型比较)

battery_info (124组电池)
  ├── battery_lifecycle_data (生命周期数据)
  └── data_statistics (统计信息)

prediction_records
  ├── models (使用的模型)
  └── battery_info (预测的电池)
```

## 注意事项

1. **数据源固定**：系统主要使用 SeversonBattery.mat 作为数据源
2. **电池编号**：1-124，已预初始化
3. **数据集划分**：
   - 训练集：偶数编号 (2, 4, 6, ..., 82) - 41组
   - 验证集：奇数编号 (1, 3, 5, ..., 83, 84) - 43组
   - 测试集：85-124号 - 40组
4. **用户权限**：所有用户具有相同的权限，无管理员/普通用户区分

## 维护建议

1. 定期运行 `check_data_consistency()` 检查数据一致性
2. 使用 `cleanup_old_data()` 清理旧数据
3. 定期更新电池统计信息：`CALL update_battery_statistics(battery_id)`
4. 监控系统健康：`CALL get_system_health_report()`

## 技术支持

如有问题，请检查：
1. 数据库连接配置
2. SeversonBattery.mat 文件路径
3. 数据导入脚本的日志输出
