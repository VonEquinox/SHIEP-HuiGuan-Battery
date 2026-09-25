#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
创建 shares 表的数据库迁移脚本
用于实现资源共享功能

使用方法:
    python migrate_shares_table.py
"""

import pymysql
import sys
import io
from datetime import datetime

# 设置标准输出编码为 UTF-8（Windows 兼容）
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ========================================
# 数据库配置（从 config.py 读取）
# ========================================
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '092155',
    'database': 'battery_soh_db',
    'charset': 'utf8mb4'
}

# ========================================
# SQL 迁移语句
# ========================================
CREATE_SHARES_TABLE_SQL = """
-- ========================================
-- 创建资源共享表 (shares)
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='资源共享表';
"""


def create_connection():
    """创建MySQL数据库连接"""
    try:
        connection = pymysql.connect(**DB_CONFIG)
        print("[OK] 数据库连接成功")
        print(f"    数据库: {DB_CONFIG['database']}")
        print(f"    主机: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        return connection
    except Exception as e:
        print(f"[ERROR] 数据库连接失败: {e}")
        print("请检查数据库配置和确保MySQL服务已启动")
        print(f"    尝试连接的配置: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
        sys.exit(1)


def check_table_exists(connection, table_name):
    """检查表是否已存在"""
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            result = cursor.fetchone()
            return result is not None
    except Exception as e:
        print(f"检查表是否存在时出错: {e}")
        return False


def create_shares_table(connection):
    """创建 shares 表"""
    try:
        with connection.cursor() as cursor:
            # 检查表是否已存在
            if check_table_exists(connection, 'shares'):
                print("[WARN] shares 表已存在，跳过创建")
                return True
            
            print("正在创建 shares 表...")
            cursor.execute(CREATE_SHARES_TABLE_SQL)
            connection.commit()
            print("[OK] shares 表创建成功")
            return True
    except Exception as e:
        print(f"[ERROR] 创建 shares 表失败: {e}")
        connection.rollback()
        return False


def verify_table_structure(connection):
    """验证表结构"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("DESCRIBE shares")
            columns = cursor.fetchall()
            print("\n[OK] shares 表结构验证:")
            print(f"  共 {len(columns)} 个字段")
            for col in columns:
                print(f"  - {col[0]}: {col[1]}")
            return True
    except Exception as e:
        print(f"[ERROR] 验证表结构失败: {e}")
        return False


def main():
    """主函数"""
    try:
        print("=" * 60)
        print("资源共享表 (shares) 数据库迁移脚本")
        print("=" * 60)
        print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # 连接数据库
        connection = create_connection()
        
        try:
            # 创建表
            if create_shares_table(connection):
                # 验证表结构
                verify_table_structure(connection)
                print("\n" + "=" * 60)
                print("[OK] 数据迁移完成！")
                print("=" * 60)
            else:
                print("\n" + "=" * 60)
                print("[ERROR] 数据迁移失败！")
                print("=" * 60)
                sys.exit(1)
        finally:
            connection.close()
            print("\n数据库连接已关闭")
    except Exception as e:
        print(f"[ERROR] 执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
