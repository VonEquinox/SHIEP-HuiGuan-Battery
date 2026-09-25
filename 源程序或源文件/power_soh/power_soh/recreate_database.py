"""
数据库重建脚本 - 根据SQLAlchemy模型直接重新创建数据库
"""
import pymysql


def recreate_database():
    """重新创建数据库和所有表"""
    
    # 数据库配置 - 请根据您的实际配置修改
    DB_HOST = 'localhost'
    DB_PORT = 3306
    DB_USER = 'root'
    DB_PASSWORD = ''  # 请输入您的MySQL root密码
    DB_NAME = 'battery_soh_backend_db'
    
    print("=" * 60)
    print("储能电池寿命预测系统 - 数据库重建工具")
    print("=" * 60)
    
    # 如果密码为空，提示用户输入
    if not DB_PASSWORD:
        DB_PASSWORD = input("请输入MySQL root密码 (直接回车表示无密码): ")
    
    try:
        # 连接MySQL服务器（不指定数据库）
        print("\n[1/4] 连接MySQL服务器...")
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            charset='utf8mb4'
        )
        print("✓ 连接成功")
        
        cursor = conn.cursor()
        
        # 删除旧数据库（如果存在）
        print("\n[2/4] 删除旧数据库（如果存在）...")
        cursor.execute(f"DROP DATABASE IF EXISTS `{DB_NAME}`")
        print(f"✓ 已删除旧数据库 '{DB_NAME}'")
        
        # 创建新数据库
        print("\n[3/4] 创建新数据库...")
        cursor.execute(
            f"CREATE DATABASE `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        print(f"✓ 已创建数据库 '{DB_NAME}'")
        
        # 切换到新数据库
        cursor.execute(f"USE `{DB_NAME}`")
        
        # 创建所有表
        print("\n[4/4] 创建数据表...")
        
        # 1. 用户表
        cursor.execute("""
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(100) NOT NULL UNIQUE,
                hashed_password VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                status TINYINT(1) NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP 
                    ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_username (username),
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
            COLLATE=utf8mb4_unicode_ci COMMENT='用户表'
        """)
        print("  ✓ users 表创建成功")
        
        # 2. 数据集表
        cursor.execute("""
            CREATE TABLE datasets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                file_path VARCHAR(255) NOT NULL,
                file_size INT,
                num_samples INT,
                feature_columns TEXT,
                target_columns TEXT,
                data_format VARCHAR(20) NOT NULL DEFAULT 'csv',
                preprocessing_steps TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP 
                    ON UPDATE CURRENT_TIMESTAMP,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
            COLLATE=utf8mb4_unicode_ci COMMENT='数据集表'
        """)
        print("  ✓ datasets 表创建成功")
        
        # 3. 电池数据表
        cursor.execute("""
            CREATE TABLE battery_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                battery_id VARCHAR(50) NOT NULL,
                capacity FLOAT NOT NULL,
                voltage FLOAT NOT NULL,
                temperature FLOAT NOT NULL,
                cycle_count INT NOT NULL,
                soc FLOAT NOT NULL,
                soh FLOAT NOT NULL,
                internal_resistance FLOAT NOT NULL,
                charge_current FLOAT NOT NULL,
                discharge_current FLOAT NOT NULL,
                charge_voltage FLOAT,
                discharge_voltage FLOAT,
                energy_efficiency FLOAT,
                peak_power FLOAT,
                self_discharge_rate FLOAT,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data_source VARCHAR(100) NOT NULL DEFAULT 'manual',
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_battery_id (battery_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
            COLLATE=utf8mb4_unicode_ci COMMENT='电池数据表'
        """)
        print("  ✓ battery_data 表创建成功")
        
        # 4. 模型表
        cursor.execute("""
            CREATE TABLE models (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                name VARCHAR(100) NOT NULL,
                algorithm_type VARCHAR(50) NOT NULL,
                framework VARCHAR(50) NOT NULL DEFAULT 'PyTorch',
                description TEXT,
                hyperparameters TEXT,
                architecture TEXT,
                input_shape TEXT,
                output_shape TEXT,
                metrics TEXT,
                trained_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) NOT NULL DEFAULT 'completed',
                model_path VARCHAR(255),
                checkpoint_path VARCHAR(255),
                model_size INT,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP 
                    ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_algorithm_type (algorithm_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
            COLLATE=utf8mb4_unicode_ci COMMENT='模型表'
        """)
        print("  ✓ models 表创建成功")
        
        # 5. 训练记录表
        cursor.execute("""
            CREATE TABLE training_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                model_id INT NOT NULL,
                dataset_path VARCHAR(255) NOT NULL,
                training_config TEXT,
                optimizer VARCHAR(50),
                learning_rate FLOAT,
                batch_size INT,
                epochs INT,
                start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                end_time DATETIME,
                duration FLOAT,
                initial_loss FLOAT,
                final_loss FLOAT,
                best_val_loss FLOAT,
                convergence_epoch INT,
                train_metrics TEXT,
                validation_metrics TEXT,
                test_metrics TEXT,
                parameters_count INT,
                memory_usage FLOAT,
                gpu_usage FLOAT,
                cpu_usage FLOAT,
                status VARCHAR(20) NOT NULL DEFAULT 'running',
                logs TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_model_id (model_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
            COLLATE=utf8mb4_unicode_ci COMMENT='训练记录表'
        """)
        print("  ✓ training_records 表创建成功")
        
        # 6. 预测记录表
        cursor.execute("""
            CREATE TABLE prediction_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                model_id INT NOT NULL,
                battery_id VARCHAR(50) NOT NULL,
                input_data TEXT,
                predicted_soh FLOAT,
                predicted_rul FLOAT,
                predicted_pcl FLOAT,
                actual_soh FLOAT,
                actual_rul FLOAT,
                actual_pcl FLOAT,
                prediction_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                execution_time FLOAT,
                confidence FLOAT,
                error_analysis TEXT,
                prediction_type VARCHAR(20) NOT NULL DEFAULT 'soh',
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_model_id (model_id),
                INDEX idx_battery_id (battery_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
            COLLATE=utf8mb4_unicode_ci COMMENT='预测记录表'
        """)
        print("  ✓ prediction_records 表创建成功")
        
        # 7. 模型比较表
        cursor.execute("""
            CREATE TABLE model_comparisons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                comparison_name VARCHAR(100) NOT NULL,
                compared_models TEXT,
                comparison_metrics TEXT,
                comparison_results TEXT,
                statistical_tests TEXT,
                visualization_data TEXT,
                created_by INT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP 
                    ON UPDATE CURRENT_TIMESTAMP,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                FOREIGN KEY (created_by) REFERENCES users(id)
                    ON DELETE CASCADE,
                INDEX idx_created_by (created_by)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
            COLLATE=utf8mb4_unicode_ci COMMENT='模型比较表'
        """)
        print("  ✓ model_comparisons 表创建成功")
        
        # 插入默认管理员用户
        # 密码: admin123 (bcrypt哈希)
        admin_hash = (
            "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4"
            ".S7fH8Z0QJH.O9S"
        )
        cursor.execute("""
            INSERT INTO users (username, email, hashed_password, role, status)
            VALUES (%s, %s, %s, %s, %s)
        """, ('admin', 'admin@battery.com', admin_hash, 'admin', 1))
        print("\n✓ 默认管理员用户已创建")
        print("  用户名: admin")
        print("  密码: admin123")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 60)
        print("数据库重建完成！")
        print("=" * 60)
        print(f"\n数据库名称: {DB_NAME}")
        print("创建的表:")
        print("  1. users - 用户表")
        print("  2. datasets - 数据集表")
        print("  3. battery_data - 电池数据表")
        print("  4. models - 模型表")
        print("  5. training_records - 训练记录表")
        print("  6. prediction_records - 预测记录表")
        print("  7. model_comparisons - 模型比较表")
        print("\n现在可以启动后端服务了！")
        
        return True
        
    except pymysql.err.OperationalError as e:
        print(f"\n✗ 数据库连接失败: {e}")
        print("\n请检查:")
        print("  1. MySQL服务是否已启动")
        print("  2. 用户名和密码是否正确")
        print("  3. 端口号是否正确 (默认3306)")
        return False
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    recreate_database()
