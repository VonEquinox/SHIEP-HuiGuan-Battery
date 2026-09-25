# 储能电池寿命预测系统 - 数据库部分

## 概述

储能电池寿命预测系统是一个基于FastAPI、PyTorch和MySQL的完整解决方案，支持用户管理、电池数据分析、模型训练和预测功能。

## 数据库架构

系统使用MySQL数据库，包含以下7个核心表：

### 1. 用户表 (users)
- 存储系统用户信息
- 支持用户角色管理（普通用户/管理员）
- 包含用户状态管理和认证信息

### 2. 电池数据表 (battery_data)
- 存储电池的各种参数（容量、电压、温度等）
- 记录电池健康状态(SOH)和荷电状态(SOC)
- 支持电池循环次数和内阻等关键指标

### 3. 模型表 (models)
- 存储深度学习模型信息
- 记录模型算法类型、框架和超参数
- 管理模型文件路径和训练状态

### 4. 训练记录表 (training_records)
- 跟踪模型训练过程
- 记录训练配置、损失值和性能指标
- 存储训练时间和资源使用情况

### 5. 预测记录表 (prediction_records)
- 存储模型预测结果
- 记录预测的SOH、RUL和PCL值
- 包含实际值对比和置信度信息

### 6. 数据集表 (datasets)
- 管理训练和测试数据集
- 记录数据集特征和预处理步骤
- 支持多种数据格式

### 7. 模型比较表 (model_comparisons)
- 存储模型比较结果
- 记录比较指标和统计检验结果
- 支持可视化数据存储

## 快速开始

### 1. 安装依赖
```bash
pip install PyMySQL
```

### 2. 配置数据库连接
编辑 `.env` 文件以匹配您的MySQL配置：
```
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=battery_soh_backend_db
```

### 3. 初始化数据库
运行以下命令初始化数据库：
```bash
python pymysql_init.py
```

或者手动执行SQL文件：
```sql
SOURCE init_database.sql;
```

## 数据库初始化脚本

系统提供了多种数据库初始化方式：

- `init_database.sql` - 核心SQL脚本
- `pymysql_init.py` - Python脚本（推荐）
- `execute_sql.py` - 命令行执行脚本
- `run_db_update.py` - 通用更新脚本

## 系统特性

- **完整的用户权限管理** - 支持多用户和角色控制
- **高效的索引设计** - 优化查询性能
- **外键约束** - 确保数据一致性
- **时间戳跟踪** - 自动记录创建和更新时间
- **JSON字段支持** - 灵活存储复杂数据结构

## 默认用户

系统创建了默认管理员账户：
- 用户名: `admin`
- 密码: `admin123` (哈希存储)

## 故障排除

如果遇到连接问题，请检查：
1. MySQL服务是否正在运行
2. 数据库凭据是否正确
3. 网络连接是否正常
4. 防火墙设置是否允许连接

更多信息请参见 `DB_SETUP_GUIDE.md`。

## 技术栈

- **数据库**: MySQL 8.0+
- **Python库**: PyMySQL, SQLAlchemy
- **后端**: FastAPI
- **前端**: Vue 3 + Element Plus

---
储能电池寿命预测系统 - 完整的电池健康状态监测与预测解决方案