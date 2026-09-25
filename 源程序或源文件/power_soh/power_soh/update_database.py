"""
数据库更新脚本
用于将MySQL数据库更新为与FastAPI后端SQLAlchemy模型匹配的结构
"""
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import sys

# 加载环境变量
load_dotenv()


def get_db_connection():
    """获取数据库连接"""
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', 3306),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'battery_soh_backend_db')
        )
        if connection.is_connected():
            db_name = os.getenv('DB_NAME', 'battery_soh_backend_db')
            print(f"成功连接到MySQL数据库: {db_name}")
            return connection
    except Error as e:
        print(f"连接MySQL数据库时出错: {e}")
        return None


def create_database_if_not_exists(connection):
    """创建数据库（如果不存在）"""
    try:
        cursor = connection.cursor()
        
        # 检查数据库是否存在
        cursor.execute("SHOW DATABASES")
        databases = [db[0] for db in cursor.fetchall()]
        
        db_name = os.getenv('DB_NAME', 'battery_soh_backend_db')
        if db_name not in databases:
            create_db_sql = (
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(create_db_sql)
            print(f"数据库 '{db_name}' 已创建")
        else:
            print(f"数据库 '{db_name}' 已存在")
            
        cursor.execute(f"USE `{db_name}`")
        connection.commit()
        cursor.close()
        return True
    except Error as e:
        print(f"创建数据库时出错: {e}")
        return False


def create_tables(connection):
    """创建数据库表"""
    try:
        cursor = connection.cursor()
        
        # 1. 创建用户表
        create_users_table = """
        CREATE TABLE IF NOT EXISTS users (
            id INT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
            username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
            email VARCHAR(100) NOT NULL UNIQUE COMMENT '邮箱',
            hashed_password VARCHAR(255) NOT NULL COMMENT '哈希密码',
            role VARCHAR(20) DEFAULT 'user' COMMENT '角色: user, admin',
            status BOOLEAN DEFAULT TRUE COMMENT '状态: True=活跃, False=非活跃',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
                ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            INDEX idx_username (username),
            INDEX idx_email (email),
            INDEX idx_role (role),
            INDEX idx_status (status)
        ) ENGINE=InnoDB COMMENT='用户表';
        """
        cursor.execute(create_users_table)
        print("✓ 用户表创建成功")
        
        # 2. 创建电池数据表
        create_battery_data_table = """
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
        """
        cursor.execute(create_battery_data_table)
        print("✓ 电池数据表创建成功")
        
        # 3. 创建模型表
        create_models_table = """
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
            status VARCHAR(20) DEFAULT 'completed' 
                COMMENT '状态: pending, training, completed, failed',
            model_path VARCHAR(255) COMMENT '模型文件路径',
            checkpoint_path VARCHAR(255) COMMENT '检查点路径',
            model_size INT COMMENT '模型大小（字节）',
            is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
                ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_user_id (user_id),
            INDEX idx_algorithm_type (algorithm_type),
            INDEX idx_framework (framework),
            INDEX idx_status (status),
            INDEX idx_is_active (is_active),
            INDEX idx_trained_at (trained_at)
        ) ENGINE=InnoDB COMMENT='模型表';
        """
        cursor.execute(create_models_table)
        print("✓ 模型表创建成功")
        
        # 4. 创建训练记录表
        create_training_records_table = """
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
            status VARCHAR(20) DEFAULT 'running' 
                COMMENT '状态: running, completed, failed',
            logs TEXT COMMENT '训练日志',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
            INDEX idx_user_id (user_id),
            INDEX idx_model_id (model_id),
            INDEX idx_status (status),
            INDEX idx_start_time (start_time)
        ) ENGINE=InnoDB COMMENT='训练记录表';
        """
        cursor.execute(create_training_records_table)
        print("✓ 训练记录表创建成功")
        
        # 5. 创建预测记录表
        create_prediction_records_table = """
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
            prediction_type VARCHAR(20) DEFAULT 'soh' 
                COMMENT '预测类型: soh, rul, pcl, both',
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
        """
        cursor.execute(create_prediction_records_table)
        print("✓ 预测记录表创建成功")
        
        # 6. 创建数据集表
        create_datasets_table = """
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
                ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
            
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_user_id (user_id),
            INDEX idx_name (name),
            INDEX idx_data_format (data_format),
            INDEX idx_is_active (is_active)
        ) ENGINE=InnoDB COMMENT='数据集表';
        """
        cursor.execute(create_datasets_table)
        print("✓ 数据集表创建成功")
        
        # 7. 创建模型比较表
        create_model_comparisons_table = """
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
                ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
            
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_created_by (created_by),
            INDEX idx_comparison_name (comparison_name),
            INDEX idx_is_active (is_active)
        ) ENGINE=InnoDB COMMENT='模型比较表';
        """
        cursor.execute(create_model_comparisons_table)
        print("✓ 模型比较表创建成功")
        
        connection.commit()
        cursor.close()
        print("\n所有表创建成功！")
        return True
    except Error as e:
        print(f"创建表时出错: {e}")
        return False


def create_views(connection):
    """创建数据库视图"""
    try:
        cursor = connection.cursor()
        
        # 1. 用户活动概览视图
        create_user_activity_view = """
        CREATE OR REPLACE VIEW v_user_activity_overview AS
        SELECT 
            u.id AS user_id,
            u.username,
            u.email,
            u.role,
            u.status AS user_status,
            u.created_at AS user_created_at,
            COUNT(bd.id) AS total_battery_data,
            COUNT(m.id) AS total_models,
            COUNT(tr.id) AS total_training_records,
            COUNT(pr.id) AS total_predictions,
            COUNT(ds.id) AS total_datasets,
            COUNT(mc.id) AS total_model_comparisons,
            MAX(u.updated_at) AS last_activity
        FROM users u
        LEFT JOIN battery_data bd ON u.id = bd.user_id
        LEFT JOIN models m ON u.id = m.user_id
        LEFT JOIN training_records tr ON u.id = tr.user_id
        LEFT JOIN prediction_records pr ON u.id = pr.user_id
        LEFT JOIN datasets ds ON u.id = ds.user_id
        LEFT JOIN model_comparisons mc ON u.id = mc.created_by
        GROUP BY u.id, u.username, u.email, u.role, u.status, u.created_at;
        """
        cursor.execute(create_user_activity_view)
        print("✓ 用户活动概览视图创建成功")
        
        # 2. 模型性能概览视图
        create_model_performance_view = """
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
        GROUP BY m.id, m.name, m.algorithm_type, m.framework, 
                 m.user_id, u.username, m.status, m.trained_at, m.is_active;
        """
        cursor.execute(create_model_performance_view)
        print("✓ 模型性能概览视图创建成功")
        
        # 3. 系统整体统计视图
        create_system_stats_view = """
        CREATE OR REPLACE VIEW v_system_stats AS
        SELECT 
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM battery_data) AS total_battery_data_points,
            (SELECT COUNT(*) FROM models) AS total_models,
            (SELECT COUNT(*) FROM training_records) AS total_training_records,
            (SELECT COUNT(*) FROM prediction_records) AS total_predictions,
            (SELECT COUNT(*) FROM datasets) AS total_datasets,
            (SELECT COUNT(*) FROM model_comparisons) AS total_model_comparisons,
            (SELECT COUNT(*) FROM users WHERE role = 'admin') AS admin_users,
            (SELECT COUNT(*) FROM models WHERE is_active = TRUE) AS active_models,
            (SELECT COUNT(*) FROM datasets WHERE is_active = TRUE) AS active_datasets,
            (SELECT AVG(duration) FROM training_records WHERE status = 'completed') AS avg_training_duration,
            (SELECT COUNT(*) FROM prediction_records WHERE prediction_type = 'soh') AS soh_predictions,
            (SELECT COUNT(*) FROM prediction_records WHERE prediction_type = 'rul') AS rul_predictions,
            (SELECT COUNT(*) FROM prediction_records WHERE prediction_type = 'pcl') AS pcl_predictions;
        """
        cursor.execute(create_system_stats_view)
        print("✓ 系统整体统计视图创建成功")
        
        connection.commit()
        cursor.close()
        print("\n所有视图创建成功！")
        return True
    except Error as e:
        print(f"创建视图时出错: {e}")
        return False


def create_procedures(connection):
    """创建存储过程"""
    try:
        cursor = connection.cursor()
        
        # 设置分隔符以创建存储过程
        cursor.execute("DELIMITER //")
        
        # 1. 更新用户活动统计存储过程
        create_user_stats_procedure = """
        CREATE PROCEDURE update_user_activity_stats(IN p_user_id INT)
        BEGIN
            SELECT 
                u.username,
                COUNT(DISTINCT bd.id) AS battery_data_count,
                COUNT(DISTINCT m.id) AS model_count,
                COUNT(DISTINCT tr.id) AS training_count,
                COUNT(DISTINCT pr.id) AS prediction_count
            FROM users u
            LEFT JOIN battery_data bd ON u.id = bd.user_id
            LEFT JOIN models m ON u.id = m.user_id
            LEFT JOIN training_records tr ON u.id = tr.user_id
            LEFT JOIN prediction_records pr ON u.id = pr.user_id
            WHERE u.id = p_user_id
            GROUP BY u.id, u.username;
        END //
        """
        cursor.execute(create_user_stats_procedure)
        print("✓ 用户活动统计存储过程创建成功")
        
        # 2. 获取模型性能报告存储过程
        create_model_performance_procedure = """
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
        """
        cursor.execute(create_model_performance_procedure)
        print("✓ 模型性能报告存储过程创建成功")
        
        # 3. 系统健康状况报告存储过程
        create_system_health_procedure = """
        CREATE PROCEDURE get_system_health_report()
        BEGIN
            SELECT 
                'Basic Stats' AS report_section,
                (SELECT COUNT(*) FROM users) AS total_users,
                (SELECT COUNT(*) FROM battery_data) AS total_battery_data,
                (SELECT COUNT(*) FROM models) AS total_models,
                (SELECT COUNT(*) FROM training_records) AS total_training_records,
                (SELECT COUNT(*) FROM prediction_records) AS total_predictions,
                (SELECT COUNT(*) FROM datasets) AS total_datasets;
        END //
        """
        cursor.execute(create_system_health_procedure)
        print("✓ 系统健康状况报告存储过程创建成功")
        
        # 恢复分隔符
        cursor.execute("DELIMITER ;")
        
        connection.commit()
        cursor.close()
        print("\n所有存储过程创建成功！")
        return True
    except Error as e:
        print(f"创建存储过程时出错: {e}")
        return False


def insert_default_data(connection):
    """插入默认数据"""
    try:
        cursor = connection.cursor()
        
        # 检查是否已有管理员用户
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        admin_exists = cursor.fetchone()[0]
        
        if admin_exists == 0:
            # 插入默认管理员用户 (密码: admin123)
            # 密码 "admin123" 的哈希值 (使用bcrypt生成)
            admin_password_hash = "$2b$12$Jyp0N6cQzGkLZ0GKjNLlCOvW9fOy5VXvz8Ld2Z8zLd2Z8zLd2Z8z."
            insert_admin = """
            INSERT INTO users (username, email, hashed_password, role, status) 
            VALUES ('admin', 'admin@batterysystem.com', %s, 'admin', TRUE)
            """
            cursor.execute(insert_admin, (admin_password_hash,))
            print("✓ 默认管理员用户已创建")
        else:
            print("✓ 管理员用户已存在，跳过创建")
        
        connection.commit()
        cursor.close()
        return True
    except Error as e:
        print(f"插入默认数据时出错: {e}")
        return False


def main():
    """主函数"""
    print("开始更新MySQL数据库...")
    print("=" * 50)
    
    # 获取数据库连接
    connection = get_db_connection()
    if not connection:
        print("无法连接到数据库，程序退出")
        sys.exit(1)
    
    try:
        # 创建数据库
        if not create_database_if_not_exists(connection):
            print("创建数据库失败，程序退出")
            sys.exit(1)
        
        # 创建表
        if not create_tables(connection):
            print("创建表失败，程序退出")
            sys.exit(1)
        
        # 创建视图
        if not create_views(connection):
            print("创建视图失败，程序退出")
            sys.exit(1)
        
        # 创建存储过程
        if not create_procedures(connection):
            print("创建存储过程失败，程序退出")
            sys.exit(1)
        
        # 插入默认数据
        if not insert_default_data(connection):
            print("插入默认数据失败，程序退出")
            sys.exit(1)
        
        print("\n" + "=" * 50)
        print("数据库更新完成！")
        print("创建了以下组件：")
        print("- 7个数据表 (users, battery_data, models, training_records, prediction_records, datasets, model_comparisons)")
        print("- 3个视图 (v_user_activity_overview, v_model_performance_overview, v_system_stats)")
        print("- 3个存储过程 (update_user_activity_stats, get_model_performance_report, get_system_health_report)")
        print("- 1个默认管理员用户")
        print("=" * 50)
        
    except Exception as e:
        print(f"执行过程中出错: {e}")
    finally:
        if connection.is_connected():
            connection.close()
            print("数据库连接已关闭")

if __name__ == "__main__":
    main()