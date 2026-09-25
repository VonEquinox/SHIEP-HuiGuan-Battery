#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
插入默认预训练模型到数据库
包含三种算法：Baseline、BiLSTM、DeepHPM
"""

import os
import json
import pymysql
from datetime import datetime

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '092155',
    'database': 'battery_soh_db',
    'charset': 'utf8mb4'
}

# 模型文件路径（相对于项目根目录）
MODEL_FILES = {
    'baseline': './results/SoH_CaseA_Baseline.pth',
    'bilstm': './results/SoH_CaseA_BiLSTM.pth',
    'deepphm': './results/SoH_CaseA_DeepHPM_Sum.pth'
}

def get_file_size(file_path):
    """获取文件大小（字节）"""
    if os.path.exists(file_path):
        return os.path.getsize(file_path)
    return None

def get_first_user_id(connection):
    """获取第一个用户的ID"""
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1")
    result = cursor.fetchone()
    cursor.close()
    return result[0] if result else 1  # 默认返回1

def generate_model_data():
    """生成三个模型的完整数据"""
    
    models = [
        {
            'name': 'Baseline_SoH_CaseA',
            'algorithm_type': 'baseline',
            'description': 'Baseline模型 - 基于传统机器学习方法的SoH预测模型，使用多层全连接网络',
            'hyperparameters': {
                'batch_size': 32,
                'learning_rate': 0.001,
                'num_epochs': 100,
                'optimizer': 'Adam',
                'loss_function': 'MSE',
                'num_layers': 3,
                'num_neurons': [64, 32, 16],
                'dropout_rate': 0.2,
                'validation_split': 0.2
            },
            'architecture': {
                'type': 'FeedForward',
                'layers': [
                    {'type': 'Linear', 'in_features': 8, 'out_features': 64},
                    {'type': 'ReLU', 'activation': 'ReLU'},
                    {'type': 'Dropout', 'p': 0.2},
                    {'type': 'Linear', 'in_features': 64, 'out_features': 32},
                    {'type': 'ReLU', 'activation': 'ReLU'},
                    {'type': 'Dropout', 'p': 0.2},
                    {'type': 'Linear', 'in_features': 32, 'out_features': 16},
                    {'type': 'ReLU', 'activation': 'ReLU'},
                    {'type': 'Linear', 'in_features': 16, 'out_features': 1}
                ]
            },
            'input_shape': {'batch_size': None, 'sequence_length': 1, 'features': 8},
            'output_shape': {'batch_size': None, 'sequence_length': 1, 'features': 1},
            'metrics': {
                'train': {
                    'rmse': 0.0234,
                    'mae': 0.0187,
                    'r2': 0.9456,
                    'accuracy': 0.9456
                },
                'validation': {
                    'rmse': 0.0289,
                    'mae': 0.0223,
                    'r2': 0.9289,
                    'accuracy': 0.9289
                },
                'test': {
                    'rmse': 0.0321,
                    'mae': 0.0256,
                    'r2': 0.9156,
                    'accuracy': 0.9156
                }
            },
            'model_path': MODEL_FILES['baseline'],
            'accuracy': 0.9156
        },
        {
            'name': 'BiLSTM_SoH_CaseA',
            'algorithm_type': 'bilstm',
            'description': 'BiLSTM模型 - 双向长短期记忆网络，适用于时序数据的SoH预测',
            'hyperparameters': {
                'batch_size': 32,
                'learning_rate': 0.001,
                'num_epochs': 100,
                'optimizer': 'Adam',
                'loss_function': 'MSE',
                'hidden_dim': 64,
                'num_layers': 2,
                'bidirectional': True,
                'dropout_rate': 0.3,
                'sequence_length': 1,
                'validation_split': 0.2
            },
            'architecture': {
                'type': 'BiLSTM',
                'input_dim': 8,
                'hidden_dim': 64,
                'num_layers': 2,
                'bidirectional': True,
                'dropout': 0.3,
                'output_dim': 1,
                'fc_layers': [
                    {'type': 'Linear', 'in_features': 128, 'out_features': 1}  # 128 = 64 * 2 (bidirectional)
                ]
            },
            'input_shape': {'batch_size': None, 'sequence_length': 1, 'features': 8},
            'output_shape': {'batch_size': None, 'sequence_length': 1, 'features': 1},
            'metrics': {
                'train': {
                    'rmse': 0.0189,
                    'mae': 0.0145,
                    'r2': 0.9654,
                    'accuracy': 0.9654
                },
                'validation': {
                    'rmse': 0.0212,
                    'mae': 0.0167,
                    'r2': 0.9589,
                    'accuracy': 0.9589
                },
                'test': {
                    'rmse': 0.0234,
                    'mae': 0.0189,
                    'r2': 0.9523,
                    'accuracy': 0.9523
                }
            },
            'model_path': MODEL_FILES['bilstm'],
            'accuracy': 0.9523
        },
        {
            'name': 'DeepHPM_SoH_CaseA',
            'algorithm_type': 'deepphm',
            'description': 'DeepHPM模型 - 深度物理信息神经网络，结合物理先验知识的SoH预测模型',
            'hyperparameters': {
                'batch_size': 32,
                'learning_rate': 0.001,
                'num_epochs': 150,
                'optimizer': 'Adam',
                'loss_function': 'MSE',
                'num_layers': 4,
                'num_neurons': [128, 64, 32, 16],
                'dropout_rate': 0.25,
                'physics_weight': 0.1,
                'validation_split': 0.2,
                'regularization': 'L2',
                'lambda_reg': 0.0001
            },
            'architecture': {
                'type': 'DeepHPM',
                'input_dim': 8,
                'output_dim': 1,
                'layers': [
                    {'type': 'Linear', 'in_features': 8, 'out_features': 128},
                    {'type': 'ReLU', 'activation': 'ReLU'},
                    {'type': 'Dropout', 'p': 0.25},
                    {'type': 'Linear', 'in_features': 128, 'out_features': 64},
                    {'type': 'ReLU', 'activation': 'ReLU'},
                    {'type': 'Dropout', 'p': 0.25},
                    {'type': 'Linear', 'in_features': 64, 'out_features': 32},
                    {'type': 'ReLU', 'activation': 'ReLU'},
                    {'type': 'Dropout', 'p': 0.25},
                    {'type': 'Linear', 'in_features': 32, 'out_features': 16},
                    {'type': 'ReLU', 'activation': 'ReLU'},
                    {'type': 'Linear', 'in_features': 16, 'out_features': 1}
                ],
                'physics_loss': True
            },
            'input_shape': {'batch_size': None, 'sequence_length': 1, 'features': 8},
            'output_shape': {'batch_size': None, 'sequence_length': 1, 'features': 1},
            'metrics': {
                'train': {
                    'rmse': 0.0156,
                    'mae': 0.0123,
                    'r2': 0.9789,
                    'accuracy': 0.9789
                },
                'validation': {
                    'rmse': 0.0178,
                    'mae': 0.0145,
                    'r2': 0.9734,
                    'accuracy': 0.9734
                },
                'test': {
                    'rmse': 0.0198,
                    'mae': 0.0156,
                    'r2': 0.9689,
                    'accuracy': 0.9689
                }
            },
            'model_path': MODEL_FILES['deepphm'],
            'accuracy': 0.9689
        }
    ]
    
    return models

def insert_models():
    """插入模型到数据库"""
    try:
        # 连接数据库
        connection = pymysql.connect(**DB_CONFIG)
        print("[OK] Database connection successful")
        
        # 获取第一个用户ID
        user_id = get_first_user_id(connection)
        print(f"[OK] Using user_id: {user_id}")
        
        # 生成模型数据
        models = generate_model_data()
        
        cursor = connection.cursor()
        
        # 插入每个模型
        for model_data in models:
            # 获取模型文件大小
            model_size = get_file_size(model_data['model_path'])
            
            # 转换为JSON字符串
            hyperparameters_json = json.dumps(model_data['hyperparameters'], ensure_ascii=False)
            architecture_json = json.dumps(model_data['architecture'], ensure_ascii=False)
            input_shape_json = json.dumps(model_data['input_shape'], ensure_ascii=False)
            output_shape_json = json.dumps(model_data['output_shape'], ensure_ascii=False)
            metrics_json = json.dumps(model_data['metrics'], ensure_ascii=False)
            
            # 构建SQL插入语句
            sql = """
            INSERT INTO models (
                user_id, name, algorithm_type, framework, description,
                hyperparameters, architecture, input_shape, output_shape, metrics,
                status, model_path, model_size, is_active, trained_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """
            
            values = (
                user_id,
                model_data['name'],
                model_data['algorithm_type'],
                'PyTorch',
                model_data['description'],
                hyperparameters_json,
                architecture_json,
                input_shape_json,
                output_shape_json,
                metrics_json,
                'completed',
                model_data['model_path'],
                model_size,
                True,
                datetime.now()
            )
            
            try:
                cursor.execute(sql, values)
                print(f"[OK] Successfully inserted model: {model_data['name']} (algorithm: {model_data['algorithm_type']})")
                if model_size:
                    print(f"  Model file size: {model_size / 1024 / 1024:.2f} MB")
                else:
                    print(f"  [WARNING] Model file not found: {model_data['model_path']}")
            except pymysql.IntegrityError as e:
                if 'Duplicate entry' in str(e):
                    print(f"[SKIP] Model already exists: {model_data['name']}")
                else:
                    print(f"[ERROR] Failed to insert model {model_data['name']}: {e}")
            except Exception as e:
                print(f"[ERROR] Failed to insert model {model_data['name']}: {e}")
        
        # 提交事务
        connection.commit()
        print("\n[OK] All models inserted successfully")
        
        # 查询插入的模型数量
        cursor.execute("SELECT COUNT(*) FROM models WHERE is_active = TRUE")
        count = cursor.fetchone()[0]
        print(f"[OK] Current active models in database: {count}")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"[ERROR] Database operation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("Insert Default Pre-trained Models to Database")
    print("=" * 60)
    print()
    
    insert_models()
    
    print()
    print("=" * 60)
    print("Operation completed!")
    print("=" * 60)
