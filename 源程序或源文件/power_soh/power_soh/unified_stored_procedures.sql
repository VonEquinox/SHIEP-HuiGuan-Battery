-- ========================================
-- 储能电池寿命预测系统数据库存储过程
-- 用于自动化数据统计和维护任务
-- 创建日期: 2026-01-08
-- ========================================

USE battery_soh_db;

DELIMITER //

-- ========================================
-- 1. 更新电池统计信息存储过程
-- ========================================
CREATE PROCEDURE update_battery_statistics(IN p_battery_id INT)
BEGIN
    INSERT INTO data_statistics (
        battery_id,
        voltage_mean, voltage_min, voltage_max, voltage_std, voltage_variance,
        current_mean, current_min, current_max, current_std, current_variance,
        temperature_mean, temperature_min, temperature_max, temperature_std, temperature_variance,
        capacity_mean, capacity_min, capacity_max, capacity_std, capacity_variance,
        resistance_mean, resistance_min, resistance_max, resistance_std, resistance_variance,
        soc_mean, soc_min, soc_max, soc_std, soc_variance,
        soh_mean, soh_min, soh_max, soh_std, soh_variance,
        power_mean, power_min, power_max, power_std, power_variance,
        rul_mean, rul_min, rul_max, rul_std,
        pcl_mean, pcl_min, pcl_max, pcl_std,
        total_cycles
    )
    SELECT 
        p_battery_id AS battery_id,
        AVG(voltage), MIN(voltage), MAX(voltage), STDDEV(voltage), VARIANCE(voltage),
        AVG(current), MIN(current), MAX(current), STDDEV(current), VARIANCE(current),
        AVG(temperature), MIN(temperature), MAX(temperature), STDDEV(temperature), VARIANCE(temperature),
        AVG(capacity), MIN(capacity), MAX(capacity), STDDEV(capacity), VARIANCE(capacity),
        AVG(resistance), MIN(resistance), MAX(resistance), STDDEV(resistance), VARIANCE(resistance),
        AVG(soc), MIN(soc), MAX(soc), STDDEV(soc), VARIANCE(soc),
        AVG(soh), MIN(soh), MAX(soh), STDDEV(soh), VARIANCE(soh),
        AVG(power), MIN(power), MAX(power), STDDEV(power), VARIANCE(power),
        AVG(rul), MIN(rul), MAX(rul), STDDEV(rul),
        AVG(pcl), MIN(pcl), MAX(pcl), STDDEV(pcl),
        MAX(cycle_count)
    FROM battery_lifecycle_data
    WHERE battery_id = p_battery_id
    ON DUPLICATE KEY UPDATE
        voltage_mean = VALUES(voltage_mean),
        voltage_min = VALUES(voltage_min),
        voltage_max = VALUES(voltage_max),
        voltage_std = VALUES(voltage_std),
        voltage_variance = VALUES(voltage_variance),
        current_mean = VALUES(current_mean),
        current_min = VALUES(current_min),
        current_max = VALUES(current_max),
        current_std = VALUES(current_std),
        current_variance = VALUES(current_variance),
        temperature_mean = VALUES(temperature_mean),
        temperature_min = VALUES(temperature_min),
        temperature_max = VALUES(temperature_max),
        temperature_std = VALUES(temperature_std),
        temperature_variance = VALUES(temperature_variance),
        capacity_mean = VALUES(capacity_mean),
        capacity_min = VALUES(capacity_min),
        capacity_max = VALUES(capacity_max),
        capacity_std = VALUES(capacity_std),
        capacity_variance = VALUES(capacity_variance),
        resistance_mean = VALUES(resistance_mean),
        resistance_min = VALUES(resistance_min),
        resistance_max = VALUES(resistance_max),
        resistance_std = VALUES(resistance_std),
        resistance_variance = VALUES(resistance_variance),
        soc_mean = VALUES(soc_mean),
        soc_min = VALUES(soc_min),
        soc_max = VALUES(soc_max),
        soc_std = VALUES(soc_std),
        soc_variance = VALUES(soc_variance),
        soh_mean = VALUES(soh_mean),
        soh_min = VALUES(soh_min),
        soh_max = VALUES(soh_max),
        soh_std = VALUES(soh_std),
        soh_variance = VALUES(soh_variance),
        power_mean = VALUES(power_mean),
        power_min = VALUES(power_min),
        power_max = VALUES(power_max),
        power_std = VALUES(power_std),
        power_variance = VALUES(power_variance),
        rul_mean = VALUES(rul_mean),
        rul_min = VALUES(rul_min),
        rul_max = VALUES(rul_max),
        rul_std = VALUES(rul_std),
        pcl_mean = VALUES(pcl_mean),
        pcl_min = VALUES(pcl_min),
        pcl_max = VALUES(pcl_max),
        pcl_std = VALUES(pcl_std),
        total_cycles = VALUES(total_cycles);
END //

-- ========================================
-- 2. 更新用户活动统计存储过程
-- ========================================
CREATE PROCEDURE update_user_activity_stats(IN p_user_id INT)
BEGIN
    SELECT 
        u.username,
        COUNT(DISTINCT m.id) AS model_count,
        COUNT(DISTINCT tr.id) AS training_count,
        COUNT(DISTINCT pr.id) AS prediction_count,
        COUNT(DISTINCT ds.id) AS dataset_count
    FROM users u
    LEFT JOIN models m ON u.id = m.user_id
    LEFT JOIN training_records tr ON u.id = tr.user_id
    LEFT JOIN prediction_records pr ON u.id = pr.user_id
    LEFT JOIN datasets ds ON u.id = ds.user_id
    WHERE u.id = p_user_id
    GROUP BY u.id, u.username;
END //

-- ========================================
-- 3. 获取模型性能报告存储过程
-- ========================================
CREATE PROCEDURE get_model_performance_report(IN p_model_id INT)
BEGIN
    SELECT 
        m.name AS model_name,
        m.algorithm_type,
        m.framework,
        COUNT(tr.id) AS total_training_sessions,
        AVG(tr.initial_loss) AS avg_initial_loss,
        AVG(tr.final_loss) AS avg_final_loss,
        AVG(tr.best_val_loss) AS avg_best_val_loss,
        AVG(tr.duration) AS avg_training_duration,
        MIN(tr.start_time) AS first_training,
        MAX(tr.end_time) AS latest_training,
        COUNT(pr.id) AS total_predictions
    FROM models m
    LEFT JOIN training_records tr ON m.id = tr.model_id
    LEFT JOIN prediction_records pr ON m.id = pr.model_id
    WHERE m.id = p_model_id OR p_model_id IS NULL
    GROUP BY m.id, m.name, m.algorithm_type, m.framework;
END //

-- ========================================
-- 4. 清理旧数据存储过程
-- ========================================
CREATE PROCEDURE cleanup_old_data(IN p_days_old INT)
BEGIN
    DECLARE v_deleted_count INT DEFAULT 0;
    
    -- 删除超过指定天数的预测记录
    DELETE FROM prediction_records 
    WHERE created_at < DATE_SUB(NOW(), INTERVAL p_days_old DAY);
    
    SET v_deleted_count = ROW_COUNT();
    
    -- 删除超过指定天数的训练记录
    DELETE FROM training_records 
    WHERE created_at < DATE_SUB(NOW(), INTERVAL p_days_old DAY);
    
    SET v_deleted_count = v_deleted_count + ROW_COUNT();
    
    SELECT CONCAT('总共删除了 ', v_deleted_count, ' 条旧数据记录') AS cleanup_result;
END //

-- ========================================
-- 5. 生成系统健康状况报告存储过程
-- ========================================
CREATE PROCEDURE get_system_health_report()
BEGIN
    -- 基本系统统计
    SELECT 
        'Basic Stats' AS report_section,
        (SELECT COUNT(*) FROM users) AS total_users,
        (SELECT COUNT(*) FROM battery_lifecycle_data) AS total_battery_data,
        (SELECT COUNT(*) FROM models) AS total_models,
        (SELECT COUNT(*) FROM training_records) AS total_training_records,
        (SELECT COUNT(*) FROM prediction_records) AS total_predictions,
        (SELECT COUNT(*) FROM datasets) AS total_datasets,
        (SELECT COUNT(*) FROM battery_info) AS total_batteries;
    
    -- 活跃用户统计
    SELECT 
        'Active Users' AS report_section,
        COUNT(*) AS active_user_count,
        (SELECT COUNT(*) FROM users WHERE status = TRUE) AS active_status_count
    FROM users WHERE status = TRUE;
    
    -- 模型状态统计
    SELECT 
        'Model Status' AS report_section,
        status,
        COUNT(*) AS count
    FROM models
    GROUP BY status;
    
    -- 最近活动统计（最近7天）
    SELECT 
        'Recent Activity (Last 7 Days)' AS report_section,
        (SELECT COUNT(*) FROM training_records WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) AS recent_training,
        (SELECT COUNT(*) FROM prediction_records WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) AS recent_predictions;
END //

-- ========================================
-- 6. 数据一致性检查存储过程
-- ========================================
CREATE PROCEDURE check_data_consistency()
BEGIN
    -- 检查孤立的模型记录
    SELECT COUNT(*) INTO @orphaned_models
    FROM models m
    LEFT JOIN users u ON m.user_id = u.id
    WHERE u.id IS NULL;
    
    -- 检查孤立的训练记录
    SELECT COUNT(*) INTO @orphaned_training
    FROM training_records tr
    LEFT JOIN users u ON tr.user_id = u.id
    LEFT JOIN models m ON tr.model_id = m.id
    WHERE u.id IS NULL OR m.id IS NULL;
    
    -- 检查孤立的预测记录
    SELECT COUNT(*) INTO @orphaned_predictions
    FROM prediction_records pr
    LEFT JOIN users u ON pr.user_id = u.id
    LEFT JOIN models m ON pr.model_id = m.id
    LEFT JOIN battery_info bi ON pr.battery_id = bi.battery_id
    WHERE u.id IS NULL OR m.id IS NULL OR bi.battery_id IS NULL;
    
    -- 检查孤立的数据集记录
    SELECT COUNT(*) INTO @orphaned_datasets
    FROM datasets ds
    LEFT JOIN users u ON ds.user_id = u.id
    WHERE u.id IS NULL;
    
    -- 检查孤立的模型比较记录
    SELECT COUNT(*) INTO @orphaned_comparisons
    FROM model_comparisons mc
    LEFT JOIN users u ON mc.created_by = u.id
    WHERE u.id IS NULL;
    
    -- 汇总不一致信息
    SELECT 
        'Data Consistency Check' AS check_type,
        @orphaned_models AS orphaned_models,
        @orphaned_training AS orphaned_training,
        @orphaned_predictions AS orphaned_predictions,
        @orphaned_datasets AS orphaned_datasets,
        @orphaned_comparisons AS orphaned_comparisons,
        (@orphaned_models + @orphaned_training + 
         @orphaned_predictions + @orphaned_datasets + @orphaned_comparisons) AS total_inconsistencies;
END //

DELIMITER ;

-- ========================================
-- 存储过程创建完成
-- ========================================
SELECT '数据库存储过程创建完成！' AS message;
