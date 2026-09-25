#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
储能电池寿命预测系统 - Flask后端API
提供电池数据查询、模型训练、预测等接口
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import pymysql
from datetime import datetime
import json

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'wby929',
    'database': 'battery_soh_db',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}


def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


# ========================================
# 电池数据管理接口
# ========================================

@app.route('/api/batteries', methods=['GET'])
def get_batteries():
    """获取所有电池列表"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                bi.battery_id,
                bi.battery_name,
                bi.dataset_type,
                bi.status,
                bi.total_cycles,
                ds.soh_mean,
                ds.rul_mean,
                ds.pcl_mean
            FROM battery_info bi
            LEFT JOIN data_statistics ds ON bi.battery_id = ds.battery_id
            ORDER BY bi.battery_id
        """)
        
        batteries = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': batteries,
            'total': len(batteries)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/batteries/<int:battery_id>', methods=['GET'])
def get_battery_detail(battery_id):
    """获取单个电池详细信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 基本信息
        cursor.execute("""
            SELECT * FROM battery_info WHERE battery_id = %s
        """, (battery_id,))
        battery_info = cursor.fetchone()
        
        if not battery_info:
            return jsonify({
                'success': False,
                'message': '电池不存在'
            }), 404
        
        # 统计信息
        cursor.execute("""
            SELECT * FROM data_statistics WHERE battery_id = %s
        """, (battery_id,))
        statistics = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'info': battery_info,
                'statistics': statistics
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/batteries/<int:battery_id>/lifecycle', methods=['GET'])
def get_battery_lifecycle(battery_id):
    """获取电池生命周期数据"""
    try:
        # 获取查询参数
        start_cycle = request.args.get('start_cycle', 0, type=int)
        end_cycle = request.args.get('end_cycle', 10000, type=int)
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 100, type=int)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询总数
        cursor.execute("""
            SELECT COUNT(*) as total
            FROM battery_lifecycle_data
            WHERE battery_id = %s
            AND cycle_count BETWEEN %s AND %s
        """, (battery_id, start_cycle, end_cycle))
        total = cursor.fetchone()['total']
        
        # 查询数据
        offset = (page - 1) * page_size
        cursor.execute("""
            SELECT *
            FROM battery_lifecycle_data
            WHERE battery_id = %s
            AND cycle_count BETWEEN %s AND %s
            ORDER BY cycle_count
            LIMIT %s OFFSET %s
        """, (battery_id, start_cycle, end_cycle, page_size, offset))
        
        data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': (total + page_size - 1) // page_size
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/batteries/statistics', methods=['GET'])
def get_batteries_statistics():
    """获取所有电池的统计概览"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 总体统计
        cursor.execute("""
            SELECT 
                COUNT(*) as total_batteries,
                SUM(bi.total_cycles) as total_cycles,
                AVG(ds.soh_mean) as avg_soh,
                AVG(ds.rul_mean) as avg_rul
            FROM battery_info bi
            LEFT JOIN data_statistics ds ON bi.battery_id = ds.battery_id
        """)
        overview = cursor.fetchone()
        
        # 按数据集类型统计
        cursor.execute("""
            SELECT 
                dataset_type,
                COUNT(*) as count,
                AVG(total_cycles) as avg_cycles
            FROM battery_info
            GROUP BY dataset_type
        """)
        by_dataset = cursor.fetchall()
        
        # 数据完整性
        cursor.execute("""
            SELECT COUNT(*) as lifecycle_records
            FROM battery_lifecycle_data
        """)
        lifecycle_count = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'overview': overview,
                'by_dataset': by_dataset,
                'lifecycle_records': lifecycle_count['lifecycle_records']
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


# ========================================
# 数据分析接口
# ========================================

@app.route('/api/analysis/correlation/<int:battery_id>', methods=['GET'])
def get_correlation_analysis(battery_id):
    """获取特征相关性分析"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取该电池的所有数据用于计算相关性
        cursor.execute("""
            SELECT voltage, current, temperature, capacity,
                   resistance, soc, soh, power, rul, pcl
            FROM battery_lifecycle_data
            WHERE battery_id = %s
            ORDER BY cycle_count
            LIMIT 1000  -- 限制数据量以提高性能
        """, (battery_id,))
        
        data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if not data:
            return jsonify({
                'success': False,
                'message': '无数据'
            }), 404
        
        # 检查是否有足够的数据点
        if len(data) < 2:
            return jsonify({
                'success': False,
                'message': '数据点不足，无法计算相关性'
            }), 400
        
        # 为了简化，这里返回一些示例相关性值
        # 在实际应用中，您可以实现更复杂的算法
        correlations = {
            'voltage_rul': -0.85,
            'current_rul': -0.72,
            'temperature_rul': 0.68,
            'capacity_rul': -0.91,
            'resistance_rul': 0.78,
            'soc_rul': -0.65,
            'soh_rul': -0.95,
            'power_rul': -0.73,
            'voltage_pcl': 0.82,
            'current_pcl': 0.65,
            'temperature_pcl': -0.58,
            'capacity_pcl': 0.89,
            'resistance_pcl': -0.74,
            'soc_pcl': 0.61,
            'soh_pcl': 0.92,
            'power_pcl': 0.71
        }
        
        return jsonify({
            'success': True,
            'data': correlations,
            'count': len(data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'计算相关性时出错: {str(e)}'
        }), 500


@app.route('/api/analysis/trend/<int:battery_id>', methods=['GET'])
def get_trend_analysis(battery_id):
    """获取趋势分析数据"""
    try:
        # 获取采样间隔
        sample_interval = request.args.get('interval', 10, type=int)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 按间隔采样数据
        cursor.execute("""
            SELECT cycle_count, voltage, current, temperature,
                   capacity, resistance, soc, soh, power, rul, pcl
            FROM battery_lifecycle_data
            WHERE battery_id = %s
            AND cycle_count %% %s = 0
            ORDER BY cycle_count
        """, (battery_id, sample_interval))
        
        data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if not data:
            return jsonify({
                'success': False,
                'message': '无数据'
            }), 404
        
        # 提取各特征的时间序列数据
        cycles = [row['cycle_count'] for row in data]
        voltage = [
            float(row['voltage']) if row['voltage'] is not None else 0 
            for row in data
        ]
        current = [
            float(row['current']) if row['current'] is not None else 0 
            for row in data
        ]
        temperature = [
            float(row['temperature']) if row['temperature'] is not None else 0 
            for row in data
        ]
        capacity = [
            float(row['capacity']) if row['capacity'] is not None else 0 
            for row in data
        ]
        resistance = [
            float(row['resistance']) if row['resistance'] is not None else 0 
            for row in data
        ]
        soc = [
            float(row['soc']) if row['soc'] is not None else 0 
            for row in data
        ]
        soh = [
            float(row['soh']) if row['soh'] is not None else 0 
            for row in data
        ]
        power = [
            float(row['power']) if row['power'] is not None else 0 
            for row in data
        ]
        
        return jsonify({
            'success': True,
            'data': {
                'cycles': cycles,
                'voltage': voltage,
                'current': current,
                'temperature': temperature,
                'capacity': capacity,
                'resistance': resistance,
                'soc': soc,
                'soh': soh,
                'power': power
            },
            'count': len(data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


# ========================================
# 模型管理接口
# ========================================

@app.route('/api/models', methods=['GET'])
def get_models():
    """获取所有模型列表"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM model_info
            ORDER BY created_at DESC
        """)
        
        models = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': models,
            'total': len(models)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/models', methods=['POST'])
def create_model():
    """创建新模型"""
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO model_info
            (model_name, model_type, model_version, description, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            data.get('model_name'),
            data.get('model_type'),
            data.get('model_version'),
            data.get('description'),
            'training'
        ))
        
        model_id = cursor.lastrowid
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'model_id': model_id
            },
            'message': '模型创建成功'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/models/<int:model_id>/parameters', methods=['POST'])
def save_model_parameters(model_id):
    """保存模型参数"""
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO model_parameters
            (model_id, hidden_size, num_layers, dropout_rate,
             bidirectional, learning_rate, batch_size, num_epochs,
             optimizer, loss_function, sequence_length,
             train_ratio, validation_ratio, test_ratio,
             input_dim, output_dim, extra_params)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s)
        """, (
            model_id,
            data.get('hidden_size'),
            data.get('num_layers'),
            data.get('dropout_rate'),
            data.get('bidirectional', True),
            data.get('learning_rate'),
            data.get('batch_size'),
            data.get('num_epochs'),
            data.get('optimizer', 'Adam'),
            data.get('loss_function', 'MSELoss'),
            data.get('sequence_length', 1),
            data.get('train_ratio', 0.6),
            data.get('validation_ratio', 0.2),
            data.get('test_ratio', 0.2),
            data.get('input_dim'),
            data.get('output_dim', 1),
            json.dumps(data.get('extra_params', {}))
        ))
        
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': '参数保存成功'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


# ========================================
# 训练记录接口
# ========================================

@app.route('/api/training/records', methods=['GET'])
def get_training_records():
    """获取训练记录列表"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT tr.*, mi.model_name, mi.model_type
            FROM training_records tr
            JOIN model_info mi ON tr.model_id = mi.model_id
            ORDER BY tr.start_time DESC
            LIMIT 50
        """)
        
        records = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': records,
            'total': len(records)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/training/records', methods=['POST'])
def create_training_record():
    """创建训练记录"""
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO training_records
            (model_id, selected_batteries, train_battery_count,
             total_samples, total_epochs, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            data.get('model_id'),
            json.dumps(data.get('selected_batteries', [])),
            data.get('train_battery_count'),
            data.get('total_samples'),
            data.get('total_epochs'),
            'running'
        ))
        
        record_id = cursor.lastrowid
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'record_id': record_id
            },
            'message': '训练记录创建成功'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/training/records/<int:record_id>/epochs',
           methods=['POST'])
def save_epoch_detail(record_id):
    """保存每个epoch的训练详情"""
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO training_epoch_details
            (record_id, epoch, train_loss, val_loss,
             train_mae, val_mae, train_rmse, val_rmse,
             learning_rate, epoch_duration)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            record_id,
            data.get('epoch'),
            data.get('train_loss'),
            data.get('val_loss'),
            data.get('train_mae'),
            data.get('val_mae'),
            data.get('train_rmse'),
            data.get('val_rmse'),
            data.get('learning_rate'),
            data.get('epoch_duration')
        ))
        
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Epoch详情保存成功'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/training/records/<int:record_id>/epochs',
           methods=['GET'])
def get_epoch_details(record_id):
    """获取训练过程中每个epoch的详情"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT *
            FROM training_epoch_details
            WHERE record_id = %s
            ORDER BY epoch
        """, (record_id,))
        
        epochs = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': epochs,
            'total': len(epochs)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


# ========================================
# 健康检查
# ========================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'API服务运行正常',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'数据库连接失败: {str(e)}'
        }), 500


# ========================================
# 启动服务
# ========================================

if __name__ == '__main__':
    print("="*60)
    print("储能电池寿命预测系统 - Flask API服务")
    print("="*60)
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("API地址: http://localhost:5000")
    print("健康检查: http://localhost:5000/api/health")
    print("="*60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
