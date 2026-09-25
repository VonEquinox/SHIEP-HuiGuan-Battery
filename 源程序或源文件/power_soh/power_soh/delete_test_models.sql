-- ========================================
-- 删除之前插入的测试模型数据
-- ========================================
-- 
-- 使用说明：
-- 执行此SQL脚本可以删除之前手动插入的测试模型数据
-- 只删除通过insert_default_models.py插入的三个模型
-- 不会删除用户通过训练平台训练生成的模型
-- ========================================

-- 删除之前插入的三个测试模型
DELETE FROM models 
WHERE name IN (
    'Baseline_SoH_CaseA',
    'BiLSTM_SoH_CaseA',
    'DeepHPM_SoH_CaseA'
)
AND algorithm_type IN ('baseline', 'bilstm', 'deepphm');

-- 查看剩余的模型（应该为空或只有用户训练的模型）
SELECT 
    id,
    name,
    algorithm_type,
    framework,
    status,
    model_path,
    created_at,
    trained_at
FROM models
ORDER BY id;
