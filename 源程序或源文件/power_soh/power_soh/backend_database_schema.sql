-- ========================================
-- 储能电池寿命预测系统数据库 (Backend SQLAlchemy Models)
-- 匹配 FastAPI 后端 SQLAlchemy 模型
-- 创建日期: 2026-01-08
-- ========================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS battery_soh_backend_db 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE battery_soh_backend_db;

-- ========================================
-- 1. 用户表 (对应 User 模型)
-- ========================================
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    email VARCHAR(100) NOT NULL UNIQUE COMMENT '邮箱',
    hashed_password VARCHAR(255) NOT NULL COMMENT '哈希密码',
    role VARCHAR(20) DEFAULT 'user' COMMENT '角色: user, admin',
    status BOOLEAN DEFAULT TRUE COMMENT '状态: True=活跃, False=非活跃',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_role (role),
    INDEX idx_status (status)
) ENGINE=InnoDB COMMENT='用户表';

-- ========================================
-- 2. 电池数据表 (对应 BatteryData 模型)
-- ========================================
CREATE TABLE IF NOT EXISTS battery_data (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '电池数据ID',
    user_id INT NOT NULL COMMENT '用户ID',
    battery_id VARCHAR(50) NOT NULL COMMENT '电池唯一标识',
    capacity FLOAT NOT NULL COMMENT '容量',
    voltage FLOAT NOT NULL COMMENT '电压',
    temperature FLOAT NOT NULL COMMENT '温度',
    cycle_count INT NOT NULL COMMENT '循环次数',
    soc FLOAT NOT NULL COMMENT 'State of Charge (荷电状态)',
    soh FLOAT NOT NULL COMMENT 'State of Health (健康状态)',
    internal_resistance FLOAT NOT NULL COMMENT '内阻',
    charge_current FLOAT NOT NULL COMMENT '充电电流',
    discharge_current FLOAT NOT NULL COMMENT '放电电流',
    charge_voltage FLOAT COMMENT '充电电压',
    discharge_voltage FLOAT COMMENT '放电电压',
    energy_efficiency FLOAT COMMENT '能效',
    peak_power FLOAT COMMENT '峰值功率',
    self_discharge_rate FLOAT COMMENT '自放电率',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '时间戳',
    data_source VARCHAR(100) DEFAULT 'manual' COMMENT '数据来源',
    notes TEXT COMMENT '备注',
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_battery_id (battery_id),
    INDEX idx_cycle_count (cycle_count),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB COMMENT='电池数据表';

-- ========================================
-- 3. 模型表 (对应 Model 模型)
-- ========================================
CREATE TABLE IF NOT EXISTS models (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '模型ID',
    user_id INT NOT NULL COMMENT '用户ID',
    name VARCHAR(100) NOT NULL COMMENT '模型名称',
    algorithm_type VARCHAR(50) NOT NULL COMMENT '算法类型',
    framework VARCHAR(50) DEFAULT 'PyTorch' COMMENT '深度学习框架',
    description TEXT COMMENT '模型描述',
    hyperparameters TEXT COMMENT '超参数 JSON字符串',
    architecture TEXT COMMENT '网络架构 JSON字符串',
    input_shape TEXT COMMENT '输入形状 JSON字符串',
    output_shape TEXT COMMENT '输出形状 JSON字符串',
    metrics TEXT COMMENT '评估指标 JSON字符串',
    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '训练完成时间',
    status VARCHAR(20) DEFAULT 'completed' COMMENT '状态: pending, training, completed, failed',
    model_path VARCHAR(255) COMMENT '模型文件路径',
    checkpoint_path VARCHAR(255) COMMENT '检查点路径',
    model_size INT COMMENT '模型大小（字节）',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_algorithm_type (algorithm_type),
    INDEX idx_framework (framework),
    INDEX idx_status (status),
    INDEX idx_is_active (is_active),
    INDEX idx_trained_at (trained_at)
) ENGINE=InnoDB COMMENT='模型表';

-- ========================================
-- 4. 训练记录表 (对应 TrainingRecord 模型)
-- ========================================
CREATE TABLE IF NOT EXISTS training_records (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '训练记录ID',
    user_id INT NOT NULL COMMENT '用户ID',
    model_id INT NOT NULL COMMENT '模型ID',
    dataset_path VARCHAR(255) NOT NULL COMMENT '数据集路径',
    training_config TEXT COMMENT '训练配置 JSON字符串',
    optimizer VARCHAR(50) COMMENT '优化器类型',
    learning_rate FLOAT COMMENT '学习率',
    batch_size INT COMMENT '批次大小',
    epochs INT COMMENT '训练轮数',
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
    end_time TIMESTAMP NULL COMMENT '结束时间',
    duration FLOAT COMMENT '训练时长（秒）',
    initial_loss FLOAT COMMENT '初始损失',
    final_loss FLOAT COMMENT '最终损失',
    best_val_loss FLOAT COMMENT '最佳验证损失',
    convergence_epoch INT COMMENT '收敛轮次',
    train_metrics TEXT COMMENT '训练指标 JSON字符串',
    validation_metrics TEXT COMMENT '验证指标 JSON字符串',
    test_metrics TEXT COMMENT '测试指标 JSON字符串',
    parameters_count INT COMMENT '参数数量',
    memory_usage FLOAT COMMENT '内存使用量（MB）',
    gpu_usage FLOAT COMMENT 'GPU使用率',
    cpu_usage FLOAT COMMENT 'CPU使用率',
    status VARCHAR(20) DEFAULT 'running' COMMENT '状态: running, completed, failed',
    logs TEXT COMMENT '训练日志',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_model_id (model_id),
    INDEX idx_status (status),
    INDEX idx_start_time (start_time)
) ENGINE=InnoDB COMMENT='训练记录表';

-- ========================================
-- 5. 预测记录表 (对应 PredictionRecord 模型)
-- ========================================
CREATE TABLE IF NOT EXISTS prediction_records (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '预测记录ID',
    user_id INT NOT NULL COMMENT '用户ID',
    model_id INT NOT NULL COMMENT '模型ID',
    battery_id VARCHAR(50) NOT NULL COMMENT '电池ID',
    input_data TEXT COMMENT '输入数据 JSON字符串',
    predicted_soh FLOAT COMMENT '预测SOH',
    predicted_rul FLOAT COMMENT '预测RUL',
    predicted_pcl FLOAT COMMENT '预测PCL（容量衰减）',
    actual_soh FLOAT COMMENT '实际SOH（如果有）',
    actual_rul FLOAT COMMENT '实际RUL（如果有）',
    actual_pcl FLOAT COMMENT '实际PCL（容量衰减）',
    prediction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '预测时间',
    execution_time FLOAT COMMENT '执行时间（毫秒）',
    confidence FLOAT COMMENT '置信度',
    error_analysis TEXT COMMENT '误差分析 JSON字符串',
    prediction_type VARCHAR(20) DEFAULT 'soh' COMMENT '预测类型: soh, rul, pcl, both',
    notes TEXT COMMENT '备注',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_model_id (model_id),
    INDEX idx_battery_id (battery_id),
    INDEX idx_prediction_type (prediction_type),
    INDEX idx_prediction_time (prediction_time)
) ENGINE=InnoDB COMMENT='预测记录表';

-- ========================================
-- 6. 数据集表 (对应 Dataset 模型)
-- ========================================
CREATE TABLE IF NOT EXISTS datasets (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '数据集ID',
    user_id INT NOT NULL COMMENT '用户ID',
    name VARCHAR(100) NOT NULL COMMENT '数据集名称',
    description TEXT COMMENT '数据集描述',
    file_path VARCHAR(255) NOT NULL COMMENT '文件路径',
    file_size INT COMMENT '文件大小（字节）',
    num_samples INT COMMENT '样本数量',
    feature_columns TEXT COMMENT '特征列名 JSON字符串',
    target_columns TEXT COMMENT '目标列名 JSON字符串',
    data_format VARCHAR(20) DEFAULT 'csv' COMMENT '数据格式',
    preprocessing_steps TEXT COMMENT '预处理步骤 JSON字符串',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_name (name),
    INDEX idx_data_format (data_format),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB COMMENT='数据集表';

-- ========================================
-- 7. 模型比较表 (对应 ModelComparison 模型)
-- ========================================
CREATE TABLE IF NOT EXISTS model_comparisons (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '比较ID',
    comparison_name VARCHAR(100) NOT NULL COMMENT '比较名称',
    compared_models TEXT COMMENT '参与比较的模型 IDs JSON字符串',
    comparison_metrics TEXT COMMENT '比较指标 JSON字符串',
    comparison_results TEXT COMMENT '比较结果 JSON字符串',
    statistical_tests TEXT COMMENT '统计检验结果 JSON字符串',
    visualization_data TEXT COMMENT '可视化数据 JSON字符串',
    created_by INT NOT NULL COMMENT '创建者ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_created_by (created_by),
    INDEX idx_comparison_name (comparison_name),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB COMMENT='模型比较表';

-- ========================================
-- 初始化默认用户 (admin用户)
-- ========================================
INSERT INTO users (username, email, hashed_password, role, status) VALUES
('admin', 'admin@batterysystem.com', '$2b$12$Jyp0N6cQzGkLZ0GKjNLlCOvW9fOy5VXvz8Ld2Z8zLd2Z8zLd2Z8z.', 'admin', TRUE)
ON DUPLICATE KEY UPDATE username=username;

-- ========================================
-- 数据库初始化完成
-- ========================================
SELECT '后端数据库初始化完成！' AS message;
SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema = 'battery_soh_backend_db';