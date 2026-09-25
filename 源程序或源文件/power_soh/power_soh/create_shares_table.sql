-- ========================================
-- 创建资源共享表 (shares)
-- 用于实现用户之间的资源共享功能
-- ========================================

-- 如果表已存在，先删除（谨慎使用）
-- DROP TABLE IF EXISTS shares;

-- 创建 shares 表
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='资源共享表';

-- 验证表是否创建成功
SELECT 'shares 表创建成功！' AS message;
SELECT COUNT(*) AS table_exists FROM information_schema.tables 
WHERE table_schema = DATABASE() AND table_name = 'shares';
