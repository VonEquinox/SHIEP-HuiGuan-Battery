-- ========================================
-- 储能电池寿命预测系统数据库视图
-- 用于快速查询和分析数据
-- 创建日期: 2026-01-08
-- ========================================

USE battery_soh_db;

-- ========================================
-- 1. 用户活动概览视图
-- ========================================
CREATE OR REPLACE VIEW v_user_activity_overview AS
SELECT 
    u.id AS user_id,
    u.username,
    u.email,
    u.status AS user_status,
    u.created_at AS user_created_at,
    COUNT(DISTINCT m.id) AS total_models,
    COUNT(DISTINCT tr.id) AS total_training_records,
    COUNT(DISTINCT pr.id) AS total_predictions,
    COUNT(DISTINCT ds.id) AS total_datasets,
    COUNT(DISTINCT mc.id) AS total_model_comparisons,
    MAX(u.updated_at) AS last_activity
FROM users u
LEFT JOIN models m ON u.id = m.user_id
LEFT JOIN training_records tr ON u.id = tr.user_id
LEFT JOIN prediction_records pr ON u.id = pr.user_id
LEFT JOIN datasets ds ON u.id = ds.user_id
LEFT JOIN model_comparisons mc ON u.id = mc.created_by
GROUP BY u.id, u.username, u.email, u.status, u.created_at;

-- ========================================
-- 2. 模型性能概览视图
-- ========================================
CREATE OR REPLACE VIEW v_model_performance_overview AS
SELECT 
    m.id AS model_id,
    m.name AS model_name,
    m.algorithm_type,
    m.framework,
    m.user_id,
    u.username AS created_by,
    m.status AS model_status,
    m.trained_at,
    m.is_active,
    COUNT(tr.id) AS total_training_sessions,
    COUNT(pr.id) AS total_predictions_made,
    AVG(tr.initial_loss) AS avg_initial_loss,
    AVG(tr.final_loss) AS avg_final_loss,
    AVG(tr.best_val_loss) AS avg_best_val_loss,
    AVG(tr.duration) AS avg_training_duration
FROM models m
LEFT JOIN users u ON m.user_id = u.id
LEFT JOIN training_records tr ON m.id = tr.model_id
LEFT JOIN prediction_records pr ON m.id = pr.model_id
GROUP BY m.id, m.name, m.algorithm_type, m.framework, m.user_id, u.username, m.status, m.trained_at, m.is_active;

-- ========================================
-- 3. 训练记录详细视图
-- ========================================
CREATE OR REPLACE VIEW v_training_detailed AS
SELECT 
    tr.id AS training_id,
    tr.user_id,
    u.username AS trainer,
    tr.model_id,
    m.name AS model_name,
    m.algorithm_type,
    tr.dataset_path,
    tr.start_time,
    tr.end_time,
    tr.duration,
    tr.initial_loss,
    tr.final_loss,
    tr.best_val_loss,
    tr.convergence_epoch,
    tr.parameters_count,
    tr.memory_usage,
    tr.gpu_usage,
    tr.cpu_usage,
    tr.status,
    tr.created_at
FROM training_records tr
JOIN users u ON tr.user_id = u.id
JOIN models m ON tr.model_id = m.id;

-- ========================================
-- 4. 预测记录详细视图
-- ========================================
CREATE OR REPLACE VIEW v_prediction_detailed AS
SELECT 
    pr.id AS prediction_id,
    pr.user_id,
    u.username AS predictor,
    pr.model_id,
    m.name AS model_name,
    m.algorithm_type,
    pr.battery_id,
    bi.battery_name,
    pr.predicted_soh,
    pr.actual_soh,
    pr.predicted_rul,
    pr.actual_rul,
    pr.predicted_pcl,
    pr.actual_pcl,
    pr.confidence,
    pr.prediction_type,
    pr.execution_time,
    pr.prediction_time,
    ABS(COALESCE(pr.predicted_soh, 0) - COALESCE(pr.actual_soh, 0)) AS soh_error,
    ABS(COALESCE(pr.predicted_rul, 0) - COALESCE(pr.actual_rul, 0)) AS rul_error,
    ABS(COALESCE(pr.predicted_pcl, 0) - COALESCE(pr.actual_pcl, 0)) AS pcl_error
FROM prediction_records pr
JOIN users u ON pr.user_id = u.id
JOIN models m ON pr.model_id = m.id
JOIN battery_info bi ON pr.battery_id = bi.battery_id;

-- ========================================
-- 5. 数据集使用情况视图
-- ========================================
CREATE OR REPLACE VIEW v_dataset_usage AS
SELECT 
    ds.id AS dataset_id,
    ds.name AS dataset_name,
    ds.description,
    ds.user_id,
    u.username AS owner,
    ds.file_path,
    ds.file_size,
    ds.num_samples,
    ds.data_format,
    ds.is_active,
    ds.created_at,
    COUNT(DISTINCT tr.id) AS used_in_training_sessions
FROM datasets ds
JOIN users u ON ds.user_id = u.id
LEFT JOIN training_records tr ON tr.dataset_path LIKE CONCAT('%', ds.name, '%')
GROUP BY ds.id, ds.name, ds.description, ds.user_id, u.username, ds.file_path, ds.file_size, ds.num_samples, ds.data_format, ds.is_active, ds.created_at;

-- ========================================
-- 6. 电池数据统计视图
-- ========================================
CREATE OR REPLACE VIEW v_battery_data_stats AS
SELECT 
    bld.battery_id,
    bi.battery_name,
    bi.dataset_type,
    COUNT(*) AS total_readings,
    AVG(bld.voltage) AS avg_voltage,
    MIN(bld.voltage) AS min_voltage,
    MAX(bld.voltage) AS max_voltage,
    AVG(bld.temperature) AS avg_temperature,
    MIN(bld.temperature) AS min_temperature,
    MAX(bld.temperature) AS max_temperature,
    AVG(bld.capacity) AS avg_capacity,
    MIN(bld.capacity) AS min_capacity,
    MAX(bld.capacity) AS max_capacity,
    AVG(bld.soh) AS avg_soh,
    MIN(bld.soh) AS min_soh,
    MAX(bld.soh) AS max_soh,
    AVG(bld.soc) AS avg_soc,
    MIN(bld.soc) AS min_soc,
    MAX(bld.soc) AS max_soc,
    AVG(bld.resistance) AS avg_resistance,
    MIN(bld.cycle_count) AS min_cycle_count,
    MAX(bld.cycle_count) AS max_cycle_count,
    AVG(bld.rul) AS avg_rul,
    AVG(bld.pcl) AS avg_pcl,
    MAX(bld.test_timestamp) AS last_reading_time
FROM battery_lifecycle_data bld
JOIN battery_info bi ON bld.battery_id = bi.battery_id
GROUP BY bld.battery_id, bi.battery_name, bi.dataset_type;

-- ========================================
-- 7. 电池综合信息视图
-- ========================================
CREATE OR REPLACE VIEW v_battery_overview AS
SELECT 
    bi.battery_id,
    bi.battery_name,
    bi.dataset_type,
    bi.status,
    bi.total_cycles,
    ds.soh_mean,
    ds.soh_min,
    ds.soh_max,
    ds.rul_mean,
    ds.pcl_mean,
    ds.data_completeness,
    ds.last_updated
FROM battery_info bi
LEFT JOIN data_statistics ds ON bi.battery_id = ds.battery_id;

-- ========================================
-- 8. 系统整体统计视图
-- ========================================
CREATE OR REPLACE VIEW v_system_stats AS
SELECT 
    (SELECT COUNT(*) FROM users) AS total_users,
    (SELECT COUNT(*) FROM battery_lifecycle_data) AS total_battery_data_points,
    (SELECT COUNT(*) FROM battery_info) AS total_batteries,
    (SELECT COUNT(*) FROM models) AS total_models,
    (SELECT COUNT(*) FROM training_records) AS total_training_records,
    (SELECT COUNT(*) FROM prediction_records) AS total_predictions,
    (SELECT COUNT(*) FROM datasets) AS total_datasets,
    (SELECT COUNT(*) FROM model_comparisons) AS total_model_comparisons,
    (SELECT COUNT(*) FROM users WHERE status = TRUE) AS active_users,
    (SELECT COUNT(*) FROM models WHERE is_active = TRUE) AS active_models,
    (SELECT COUNT(*) FROM datasets WHERE is_active = TRUE) AS active_datasets,
    (SELECT AVG(duration) FROM training_records WHERE status = 'completed') AS avg_training_duration,
    (SELECT COUNT(*) FROM prediction_records WHERE prediction_type = 'soh') AS soh_predictions,
    (SELECT COUNT(*) FROM prediction_records WHERE prediction_type = 'rul') AS rul_predictions,
    (SELECT COUNT(*) FROM prediction_records WHERE prediction_type = 'pcl') AS pcl_predictions;

-- ========================================
-- 视图创建完成
-- ========================================
SELECT '数据库视图创建完成！' AS message;
