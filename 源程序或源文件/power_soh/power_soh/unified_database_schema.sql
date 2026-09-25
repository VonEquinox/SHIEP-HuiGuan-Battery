-- ========================================
-- 储能电池寿命预测系统统一数据库架构
-- 基于 SeversonBattery.mat 数据文件
-- 创建日期: 2026-01-08
-- ========================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS battery_soh_db 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE battery_soh_db;

-- ========================================
-- 1. 用户表 (简化版，移除管理员角色)
-- ========================================
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    email VARCHAR(100) NOT NULL UNIQUE COMMENT '邮箱',
    hashed_password VARCHAR(255) NOT NULL COMMENT '哈希密码',
    status BOOLEAN DEFAULT TRUE COMMENT '状态: True=活跃, False=非活跃',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_status (status)
) ENGINE=InnoDB COMMENT='用户表';

-- ========================================
-- 2. 电池基本信息表 (124组电池)
-- ========================================
CREATE TABLE IF NOT EXISTS battery_info (
    battery_id INT PRIMARY KEY COMMENT '电池组编号 (1-124)',
    battery_name VARCHAR(100) NOT NULL COMMENT '电池组名称',
    manufacturer VARCHAR(100) DEFAULT 'Severson Lab' COMMENT '制造商',
    model VARCHAR(50) DEFAULT 'LFP/Graphite' COMMENT '型号',
    rated_capacity DECIMAL(10, 4) DEFAULT 1.1 COMMENT '额定容量(Ah)',
    rated_voltage DECIMAL(10, 4) DEFAULT 3.3 COMMENT '额定电压(V)',
    manufacture_date DATE COMMENT '生产日期',
    first_use_date DATE COMMENT '首次使用日期',
    status ENUM('active', 'retired', 'testing') DEFAULT 'active' COMMENT '状态',
    dataset_type ENUM('train', 'validation', 'test') NOT NULL COMMENT '数据集类型',
    total_cycles INT DEFAULT 0 COMMENT '总循环次数',
    notes TEXT COMMENT '备注信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_status (status),
    INDEX idx_dataset_type (dataset_type),
    INDEX idx_battery_name (battery_name)
) ENGINE=InnoDB COMMENT='电池基本信息表';

-- ========================================
-- 3. 电池生命周期数据表 (来自 SeversonBattery.mat)
-- ========================================
CREATE TABLE IF NOT EXISTS battery_lifecycle_data (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    battery_id INT NOT NULL COMMENT '电池组编号',
    cycle_count INT NOT NULL COMMENT '循环次数',
    
    -- 8项特征数据 (来自 Features_mov_Flt)
    voltage DECIMAL(10, 4) NOT NULL COMMENT '电压(V)',
    current DECIMAL(10, 4) NOT NULL COMMENT '电流(A)',
    temperature DECIMAL(10, 4) NOT NULL COMMENT '温度(°C)',
    capacity DECIMAL(10, 4) NOT NULL COMMENT '容量(Ah)',
    resistance DECIMAL(10, 4) NOT NULL COMMENT '内阻(mΩ)',
    soc DECIMAL(10, 4) NOT NULL COMMENT 'SOC-荷电状态(%)',
    soh DECIMAL(10, 4) NOT NULL COMMENT 'SOH-健康状态(%)',
    power DECIMAL(10, 4) NOT NULL COMMENT '功率(W)',
    
    -- 预测目标 (来自 SeversonBattery.mat)
    rul INT NOT NULL COMMENT 'RUL-剩余使用寿命(循环次数)',
    pcl DECIMAL(10, 4) NOT NULL COMMENT 'PCL-容量衰减百分比(%)',
    
    -- 时间戳
    test_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '测试时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    FOREIGN KEY (battery_id) REFERENCES battery_info(battery_id) ON DELETE CASCADE,
    UNIQUE KEY uk_battery_cycle (battery_id, cycle_count),
    INDEX idx_battery_id (battery_id),
    INDEX idx_cycle_count (cycle_count),
    INDEX idx_rul (rul),
    INDEX idx_pcl (pcl),
    INDEX idx_soh (soh),
    INDEX idx_test_timestamp (test_timestamp)
) ENGINE=InnoDB COMMENT='电池生命周期数据表';

-- ========================================
-- 4. 模型表 (用户创建的模型)
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
-- 5. 训练记录表
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
-- 6. 预测记录表
-- ========================================
CREATE TABLE IF NOT EXISTS prediction_records (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '预测记录ID',
    user_id INT NOT NULL COMMENT '用户ID',
    model_id INT NOT NULL COMMENT '模型ID',
    battery_id INT NOT NULL COMMENT '电池ID',
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
    FOREIGN KEY (battery_id) REFERENCES battery_info(battery_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_model_id (model_id),
    INDEX idx_battery_id (battery_id),
    INDEX idx_prediction_type (prediction_type),
    INDEX idx_prediction_time (prediction_time)
) ENGINE=InnoDB COMMENT='预测记录表';

-- ========================================
-- 7. 数据集表
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
-- 8. 模型比较表
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
-- 9. 数据统计表
-- ========================================
CREATE TABLE IF NOT EXISTS data_statistics (
    stat_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '统计ID',
    battery_id INT NOT NULL COMMENT '电池组编号',
    
    -- 电压统计
    voltage_mean DECIMAL(10, 4) COMMENT '电压均值',
    voltage_variance DECIMAL(10, 4) COMMENT '电压方差',
    voltage_min DECIMAL(10, 4) COMMENT '电压最小值',
    voltage_max DECIMAL(10, 4) COMMENT '电压最大值',
    voltage_std DECIMAL(10, 4) COMMENT '电压标准差',
    
    -- 电流统计
    current_mean DECIMAL(10, 4) COMMENT '电流均值',
    current_variance DECIMAL(10, 4) COMMENT '电流方差',
    current_min DECIMAL(10, 4) COMMENT '电流最小值',
    current_max DECIMAL(10, 4) COMMENT '电流最大值',
    current_std DECIMAL(10, 4) COMMENT '电流标准差',
    
    -- 温度统计
    temperature_mean DECIMAL(10, 4) COMMENT '温度均值',
    temperature_variance DECIMAL(10, 4) COMMENT '温度方差',
    temperature_min DECIMAL(10, 4) COMMENT '温度最小值',
    temperature_max DECIMAL(10, 4) COMMENT '温度最大值',
    temperature_std DECIMAL(10, 4) COMMENT '温度标准差',
    
    -- 容量统计
    capacity_mean DECIMAL(10, 4) COMMENT '容量均值',
    capacity_variance DECIMAL(10, 4) COMMENT '容量方差',
    capacity_min DECIMAL(10, 4) COMMENT '容量最小值',
    capacity_max DECIMAL(10, 4) COMMENT '容量最大值',
    capacity_std DECIMAL(10, 4) COMMENT '容量标准差',
    
    -- 内阻统计
    resistance_mean DECIMAL(10, 4) COMMENT '内阻均值',
    resistance_variance DECIMAL(10, 4) COMMENT '内阻方差',
    resistance_min DECIMAL(10, 4) COMMENT '内阻最小值',
    resistance_max DECIMAL(10, 4) COMMENT '内阻最大值',
    resistance_std DECIMAL(10, 4) COMMENT '内阻标准差',
    
    -- SOC统计
    soc_mean DECIMAL(10, 4) COMMENT 'SOC均值',
    soc_variance DECIMAL(10, 4) COMMENT 'SOC方差',
    soc_min DECIMAL(10, 4) COMMENT 'SOC最小值',
    soc_max DECIMAL(10, 4) COMMENT 'SOC最大值',
    soc_std DECIMAL(10, 4) COMMENT 'SOC标准差',
    
    -- SOH统计
    soh_mean DECIMAL(10, 4) COMMENT 'SOH均值',
    soh_variance DECIMAL(10, 4) COMMENT 'SOH方差',
    soh_min DECIMAL(10, 4) COMMENT 'SOH最小值',
    soh_max DECIMAL(10, 4) COMMENT 'SOH最大值',
    soh_std DECIMAL(10, 4) COMMENT 'SOH标准差',
    
    -- 功率统计
    power_mean DECIMAL(10, 4) COMMENT '功率均值',
    power_variance DECIMAL(10, 4) COMMENT '功率方差',
    power_min DECIMAL(10, 4) COMMENT '功率最小值',
    power_max DECIMAL(10, 4) COMMENT '功率最大值',
    power_std DECIMAL(10, 4) COMMENT '功率标准差',
    
    -- RUL和PCL统计
    rul_mean DECIMAL(10, 4) COMMENT 'RUL均值',
    rul_min INT COMMENT 'RUL最小值',
    rul_max INT COMMENT 'RUL最大值',
    rul_std DECIMAL(10, 4) COMMENT 'RUL标准差',
    
    pcl_mean DECIMAL(10, 4) COMMENT 'PCL均值',
    pcl_min DECIMAL(10, 4) COMMENT 'PCL最小值',
    pcl_max DECIMAL(10, 4) COMMENT 'PCL最大值',
    pcl_std DECIMAL(10, 4) COMMENT 'PCL标准差',
    
    -- 元信息
    total_cycles INT COMMENT '总循环次数',
    data_completeness DECIMAL(5, 4) DEFAULT 1.0000 COMMENT '数据完整性(%)',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    
    FOREIGN KEY (battery_id) REFERENCES battery_info(battery_id) ON DELETE CASCADE,
    UNIQUE KEY uk_battery_id (battery_id)
) ENGINE=InnoDB COMMENT='数据统计表';

-- ========================================
-- 初始化电池基本信息（1-124号）
-- ========================================

-- 训练集：偶数编号 (2, 4, 6, ..., 82) - 41组
INSERT INTO battery_info (battery_id, battery_name, dataset_type, status) VALUES
(2, 'Battery_002', 'train', 'active'),
(4, 'Battery_004', 'train', 'active'),
(6, 'Battery_006', 'train', 'active'),
(8, 'Battery_008', 'train', 'active'),
(10, 'Battery_010', 'train', 'active'),
(12, 'Battery_012', 'train', 'active'),
(14, 'Battery_014', 'train', 'active'),
(16, 'Battery_016', 'train', 'active'),
(18, 'Battery_018', 'train', 'active'),
(20, 'Battery_020', 'train', 'active'),
(22, 'Battery_022', 'train', 'active'),
(24, 'Battery_024', 'train', 'active'),
(26, 'Battery_026', 'train', 'active'),
(28, 'Battery_028', 'train', 'active'),
(30, 'Battery_030', 'train', 'active'),
(32, 'Battery_032', 'train', 'active'),
(34, 'Battery_034', 'train', 'active'),
(36, 'Battery_036', 'train', 'active'),
(38, 'Battery_038', 'train', 'active'),
(40, 'Battery_040', 'train', 'active'),
(42, 'Battery_042', 'train', 'active'),
(44, 'Battery_044', 'train', 'active'),
(46, 'Battery_046', 'train', 'active'),
(48, 'Battery_048', 'train', 'active'),
(50, 'Battery_050', 'train', 'active'),
(52, 'Battery_052', 'train', 'active'),
(54, 'Battery_054', 'train', 'active'),
(56, 'Battery_056', 'train', 'active'),
(58, 'Battery_058', 'train', 'active'),
(60, 'Battery_060', 'train', 'active'),
(62, 'Battery_062', 'train', 'active'),
(64, 'Battery_064', 'train', 'active'),
(66, 'Battery_066', 'train', 'active'),
(68, 'Battery_068', 'train', 'active'),
(70, 'Battery_070', 'train', 'active'),
(72, 'Battery_072', 'train', 'active'),
(74, 'Battery_074', 'train', 'active'),
(76, 'Battery_076', 'train', 'active'),
(78, 'Battery_078', 'train', 'active'),
(80, 'Battery_080', 'train', 'active'),
(82, 'Battery_082', 'train', 'active')
ON DUPLICATE KEY UPDATE battery_name=battery_name;

-- 验证集：奇数编号 (1, 3, 5, ..., 83, 84) - 43组
INSERT INTO battery_info (battery_id, battery_name, dataset_type, status) VALUES
(1, 'Battery_001', 'validation', 'active'),
(3, 'Battery_003', 'validation', 'active'),
(5, 'Battery_005', 'validation', 'active'),
(7, 'Battery_007', 'validation', 'active'),
(9, 'Battery_009', 'validation', 'active'),
(11, 'Battery_011', 'validation', 'active'),
(13, 'Battery_013', 'validation', 'active'),
(15, 'Battery_015', 'validation', 'active'),
(17, 'Battery_017', 'validation', 'active'),
(19, 'Battery_019', 'validation', 'active'),
(21, 'Battery_021', 'validation', 'active'),
(23, 'Battery_023', 'validation', 'active'),
(25, 'Battery_025', 'validation', 'active'),
(27, 'Battery_027', 'validation', 'active'),
(29, 'Battery_029', 'validation', 'active'),
(31, 'Battery_031', 'validation', 'active'),
(33, 'Battery_033', 'validation', 'active'),
(35, 'Battery_035', 'validation', 'active'),
(37, 'Battery_037', 'validation', 'active'),
(39, 'Battery_039', 'validation', 'active'),
(41, 'Battery_041', 'validation', 'active'),
(43, 'Battery_043', 'validation', 'active'),
(45, 'Battery_045', 'validation', 'active'),
(47, 'Battery_047', 'validation', 'active'),
(49, 'Battery_049', 'validation', 'active'),
(51, 'Battery_051', 'validation', 'active'),
(53, 'Battery_053', 'validation', 'active'),
(55, 'Battery_055', 'validation', 'active'),
(57, 'Battery_057', 'validation', 'active'),
(59, 'Battery_059', 'validation', 'active'),
(61, 'Battery_061', 'validation', 'active'),
(63, 'Battery_063', 'validation', 'active'),
(65, 'Battery_065', 'validation', 'active'),
(67, 'Battery_067', 'validation', 'active'),
(69, 'Battery_069', 'validation', 'active'),
(71, 'Battery_071', 'validation', 'active'),
(73, 'Battery_073', 'validation', 'active'),
(75, 'Battery_075', 'validation', 'active'),
(77, 'Battery_077', 'validation', 'active'),
(79, 'Battery_079', 'validation', 'active'),
(81, 'Battery_081', 'validation', 'active'),
(83, 'Battery_083', 'validation', 'active'),
(84, 'Battery_084', 'validation', 'active')
ON DUPLICATE KEY UPDATE battery_name=battery_name;

-- 测试集：85-124号 - 40组
INSERT INTO battery_info (battery_id, battery_name, dataset_type, status) VALUES
(85, 'Battery_085', 'test', 'active'),
(86, 'Battery_086', 'test', 'active'),
(87, 'Battery_087', 'test', 'active'),
(88, 'Battery_088', 'test', 'active'),
(89, 'Battery_089', 'test', 'active'),
(90, 'Battery_090', 'test', 'active'),
(91, 'Battery_091', 'test', 'active'),
(92, 'Battery_092', 'test', 'active'),
(93, 'Battery_093', 'test', 'active'),
(94, 'Battery_094', 'test', 'active'),
(95, 'Battery_095', 'test', 'active'),
(96, 'Battery_096', 'test', 'active'),
(97, 'Battery_097', 'test', 'active'),
(98, 'Battery_098', 'test', 'active'),
(99, 'Battery_099', 'test', 'active'),
(100, 'Battery_100', 'test', 'active'),
(101, 'Battery_101', 'test', 'active'),
(102, 'Battery_102', 'test', 'active'),
(103, 'Battery_103', 'test', 'active'),
(104, 'Battery_104', 'test', 'active'),
(105, 'Battery_105', 'test', 'active'),
(106, 'Battery_106', 'test', 'active'),
(107, 'Battery_107', 'test', 'active'),
(108, 'Battery_108', 'test', 'active'),
(109, 'Battery_109', 'test', 'active'),
(110, 'Battery_110', 'test', 'active'),
(111, 'Battery_111', 'test', 'active'),
(112, 'Battery_112', 'test', 'active'),
(113, 'Battery_113', 'test', 'active'),
(114, 'Battery_114', 'test', 'active'),
(115, 'Battery_115', 'test', 'active'),
(116, 'Battery_116', 'test', 'active'),
(117, 'Battery_117', 'test', 'active'),
(118, 'Battery_118', 'test', 'active'),
(119, 'Battery_119', 'test', 'active'),
(120, 'Battery_120', 'test', 'active'),
(121, 'Battery_121', 'test', 'active'),
(122, 'Battery_122', 'test', 'active'),
(123, 'Battery_123', 'test', 'active'),
(124, 'Battery_124', 'test', 'active')
ON DUPLICATE KEY UPDATE battery_name=battery_name;

-- ========================================
-- 10. 资源共享表
-- ========================================
CREATE TABLE IF NOT EXISTS shares (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '分享ID',
    resource_type VARCHAR(50) NOT NULL COMMENT '资源类型: model/dataset/prediction/training',
    resource_id INT NOT NULL COMMENT '资源ID',
    owner_id INT NOT NULL COMMENT '资源所有者ID',
    shared_with_user_id INT COMMENT '被分享的用户ID（NULL表示公开分享）',
    permission VARCHAR(20) DEFAULT 'read' NOT NULL COMMENT '权限: read=只读, write=读写',
    notes TEXT COMMENT '分享备注',
    expires_at TIMESTAMP NULL COMMENT '分享过期时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_active BOOLEAN DEFAULT TRUE NOT NULL COMMENT '是否激活',
    
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (shared_with_user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_resource (resource_type, resource_id),
    INDEX idx_owner_id (owner_id),
    INDEX idx_shared_with_user_id (shared_with_user_id),
    INDEX idx_is_active (is_active),
    INDEX idx_created_at (created_at),
    UNIQUE KEY uk_share_resource_user (resource_type, resource_id, shared_with_user_id, owner_id)
) ENGINE=InnoDB COMMENT='资源共享表';

-- ========================================
-- 数据库初始化完成
-- ========================================
SELECT '统一数据库架构初始化完成！' AS message;
SELECT COUNT(*) AS battery_count FROM battery_info;
