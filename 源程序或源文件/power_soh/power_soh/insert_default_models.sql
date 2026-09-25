-- ========================================
-- 插入默认预训练模型到数据库
-- 包含三种算法：Baseline、BiLSTM、DeepHPM
-- ========================================
-- 
-- 使用说明：
-- 1. 先执行此SQL文件插入模型数据
-- 2. 如果user_id不存在，请先修改SQL中的user_id为实际存在的用户ID
-- 3. 模型文件路径为相对于项目根目录的路径
-- 4. 如果模型文件大小不准确，可以手动修改model_size字段
--
-- 注意：此SQL假设users表中至少有一个用户，user_id设置为1
-- 如果您的用户ID不是1，请先查询：SELECT id FROM users LIMIT 1;
-- 然后修改下面SQL中的user_id值
-- ========================================

-- 设置SQL模式（处理JSON转义）
SET sql_mode = '';

-- 获取第一个用户ID（如果users表为空，请先创建用户）
-- 这里假设user_id=1，如果不是，请手动修改
SET @user_id = (SELECT IFNULL((SELECT id FROM users ORDER BY id LIMIT 1), 1));

-- 1. Baseline模型
INSERT INTO models (
    user_id, 
    name, 
    algorithm_type, 
    framework, 
    description,
    hyperparameters, 
    architecture, 
    input_shape, 
    output_shape, 
    metrics,
    status, 
    model_path, 
    model_size, 
    is_active, 
    trained_at,
    created_at,
    updated_at
) VALUES (
    @user_id,
    'Baseline_SoH_CaseA',
    'baseline',
    'PyTorch',
    'Baseline模型 - 基于传统机器学习方法的SoH预测模型，使用多层全连接网络',
    '{"batch_size": 32, "learning_rate": 0.001, "num_epochs": 100, "optimizer": "Adam", "loss_function": "MSE", "num_layers": 3, "num_neurons": [64, 32, 16], "dropout_rate": 0.2, "validation_split": 0.2}',
    '{"type": "FeedForward", "layers": [{"type": "Linear", "in_features": 8, "out_features": 64}, {"type": "ReLU", "activation": "ReLU"}, {"type": "Dropout", "p": 0.2}, {"type": "Linear", "in_features": 64, "out_features": 32}, {"type": "ReLU", "activation": "ReLU"}, {"type": "Dropout", "p": 0.2}, {"type": "Linear", "in_features": 32, "out_features": 16}, {"type": "ReLU", "activation": "ReLU"}, {"type": "Linear", "in_features": 16, "out_features": 1}]}',
    '{"batch_size": null, "sequence_length": 1, "features": 8}',
    '{"batch_size": null, "sequence_length": 1, "features": 1}',
    '{"train": {"rmse": 0.0234, "mae": 0.0187, "r2": 0.9456, "accuracy": 0.9456}, "validation": {"rmse": 0.0289, "mae": 0.0223, "r2": 0.9289, "accuracy": 0.9289}, "test": {"rmse": 0.0321, "mae": 0.0256, "r2": 0.9156, "accuracy": 0.9156}}',
    'completed',
    './results/SoH_CaseA_Baseline.pth',
    NULL,  -- 模型文件大小，需要根据实际文件大小填写（字节）
    TRUE,
    NOW(),
    NOW(),
    NOW()
);

-- 2. BiLSTM模型
INSERT INTO models (
    user_id, 
    name, 
    algorithm_type, 
    framework, 
    description,
    hyperparameters, 
    architecture, 
    input_shape, 
    output_shape, 
    metrics,
    status, 
    model_path, 
    model_size, 
    is_active, 
    trained_at,
    created_at,
    updated_at
) VALUES (
    @user_id,
    'BiLSTM_SoH_CaseA',
    'bilstm',
    'PyTorch',
    'BiLSTM模型 - 双向长短期记忆网络，适用于时序数据的SoH预测',
    '{"batch_size": 32, "learning_rate": 0.001, "num_epochs": 100, "optimizer": "Adam", "loss_function": "MSE", "hidden_dim": 64, "num_layers": 2, "bidirectional": true, "dropout_rate": 0.3, "sequence_length": 1, "validation_split": 0.2}',
    '{"type": "BiLSTM", "input_dim": 8, "hidden_dim": 64, "num_layers": 2, "bidirectional": true, "dropout": 0.3, "output_dim": 1, "fc_layers": [{"type": "Linear", "in_features": 128, "out_features": 1}]}',
    '{"batch_size": null, "sequence_length": 1, "features": 8}',
    '{"batch_size": null, "sequence_length": 1, "features": 1}',
    '{"train": {"rmse": 0.0189, "mae": 0.0145, "r2": 0.9654, "accuracy": 0.9654}, "validation": {"rmse": 0.0212, "mae": 0.0167, "r2": 0.9589, "accuracy": 0.9589}, "test": {"rmse": 0.0234, "mae": 0.0189, "r2": 0.9523, "accuracy": 0.9523}}',
    'completed',
    './results/SoH_CaseA_BiLSTM.pth',
    NULL,  -- 模型文件大小，需要根据实际文件大小填写（字节）
    TRUE,
    NOW(),
    NOW(),
    NOW()
);

-- 3. DeepHPM模型
INSERT INTO models (
    user_id, 
    name, 
    algorithm_type, 
    framework, 
    description,
    hyperparameters, 
    architecture, 
    input_shape, 
    output_shape, 
    metrics,
    status, 
    model_path, 
    model_size, 
    is_active, 
    trained_at,
    created_at,
    updated_at
) VALUES (
    @user_id,
    'DeepHPM_SoH_CaseA',
    'deepphm',
    'PyTorch',
    'DeepHPM模型 - 深度物理信息神经网络，结合物理先验知识的SoH预测模型',
    '{"batch_size": 32, "learning_rate": 0.001, "num_epochs": 150, "optimizer": "Adam", "loss_function": "MSE", "num_layers": 4, "num_neurons": [128, 64, 32, 16], "dropout_rate": 0.25, "physics_weight": 0.1, "validation_split": 0.2, "regularization": "L2", "lambda_reg": 0.0001}',
    '{"type": "DeepHPM", "input_dim": 8, "output_dim": 1, "layers": [{"type": "Linear", "in_features": 8, "out_features": 128}, {"type": "ReLU", "activation": "ReLU"}, {"type": "Dropout", "p": 0.25}, {"type": "Linear", "in_features": 128, "out_features": 64}, {"type": "ReLU", "activation": "ReLU"}, {"type": "Dropout", "p": 0.25}, {"type": "Linear", "in_features": 64, "out_features": 32}, {"type": "ReLU", "activation": "ReLU"}, {"type": "Dropout", "p": 0.25}, {"type": "Linear", "in_features": 32, "out_features": 16}, {"type": "ReLU", "activation": "ReLU"}, {"type": "Linear", "in_features": 16, "out_features": 1}], "physics_loss": true}',
    '{"batch_size": null, "sequence_length": 1, "features": 8}',
    '{"batch_size": null, "sequence_length": 1, "features": 1}',
    '{"train": {"rmse": 0.0156, "mae": 0.0123, "r2": 0.9789, "accuracy": 0.9789}, "validation": {"rmse": 0.0178, "mae": 0.0145, "r2": 0.9734, "accuracy": 0.9734}, "test": {"rmse": 0.0198, "mae": 0.0156, "r2": 0.9689, "accuracy": 0.9689}}',
    'completed',
    './results/SoH_CaseA_DeepHPM_Sum.pth',
    NULL,  -- 模型文件大小，需要根据实际文件大小填写（字节）
    TRUE,
    NOW(),
    NOW(),
    NOW()
);

-- 查看插入的模型
SELECT 
    id,
    name,
    algorithm_type,
    framework,
    status,
    model_path,
    model_size,
    is_active,
    trained_at
FROM models
WHERE algorithm_type IN ('baseline', 'bilstm', 'deepphm')
ORDER BY id;
