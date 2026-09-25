#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
电池数据导入MySQL脚本
从SeversonBattery.mat文件导入124组电池的完整生命周期数据到MySQL数据库

使用方法:
    python import_data_to_mysql.py

依赖:
    pip install scipy numpy pymysql tqdm
"""

import scipy.io
import numpy as np
import pymysql
from tqdm import tqdm
import sys
from datetime import datetime

# ========================================
# 数据库配置
# ========================================
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '092155',  # 请修改为您的MySQL密码
    'database': 'battery_soh_db',
    'charset': 'utf8mb4'
}

# ========================================
# 数据文件路径
# ========================================
MAT_FILE_PATH = './SeversonBattery.mat'

# ========================================
# 加载MAT文件数据
# ========================================


def load_mat_data(file_path):
    """加载.mat格式的电池数据"""
    print(f"正在加载数据文件: {file_path}")
    try:
        data = scipy.io.loadmat(file_path)
        print("✓ 数据文件加载成功")
        return data
    except Exception as e:
        print(f"✗ 加载数据文件失败: {e}")
        sys.exit(1)

# ========================================
# 数据库连接
# ========================================


def create_connection():
    """创建MySQL数据库连接"""
    try:
        connection = pymysql.connect(**DB_CONFIG)
        print("✓ 数据库连接成功")
        return connection
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        print("请检查数据库配置和确保MySQL服务已启动")
        sys.exit(1)

# ========================================
# 解析电池数据
# ========================================


def parse_battery_data(data):
    """解析MAT文件中的电池数据"""
    print("\n正在解析电池数据...")
    
    # 提取基本数据
    features = data['Features_mov_Flt']
    rul = data['RUL_Flt']
    pcl = data['PCL_Flt']
    cycles = data['Cycles_Flt']
    num_cycles_all = data['Num_Cycles_Flt'].flatten()
    
    # 获取数据集划分索引
    train_ind = data['train_ind'].flatten() - 1  # MATLAB索引从1开始
    val_ind = data['test_ind'].flatten() - 1
    test_ind = data['secondary_test_ind'].flatten() - 1
    
    num_cells = len(num_cycles_all)
    print(f"✓ 电池总数: {num_cells}")
    print(f"  - 训练集: {len(train_ind)}组")
    print(f"  - 验证集: {len(val_ind)}组")
    print(f"  - 测试集: {len(test_ind)}组")
    
    return {
        'features': features,
        'rul': rul,
        'pcl': pcl,
        'cycles': cycles,
        'num_cycles_all': num_cycles_all,
        'num_cells': num_cells,
        'train_ind': train_ind,
        'val_ind': val_ind,
        'test_ind': test_ind
    }

# ========================================
# 组织每个电池的数据
# ========================================


def organize_battery_units(battery_data):
    """将数据按电池单元组织"""
    print("\n正在组织电池单元数据...")
    
    features = battery_data['features']
    rul = battery_data['rul']
    pcl = battery_data['pcl']
    cycles = battery_data['cycles']
    num_cycles_all = battery_data['num_cycles_all']
    num_cells = battery_data['num_cells']
    
    battery_units = []
    current_idx = 0
    
    for cell_idx in range(num_cells):
        num_cycles = int(num_cycles_all[cell_idx])
        end_idx = current_idx + num_cycles
        
        # 提取该电池的数据
        cell_features = features[current_idx:end_idx, :]
        cell_rul = rul[current_idx:end_idx, :]
        cell_pcl = pcl[current_idx:end_idx, :]
        cell_cycles = cycles[current_idx:end_idx]
        
        # 假设特征顺序为:
        # [voltage, current, temp, capacity, resistance, soc, soh, power]
        # 如果实际顺序不同，需要根据数据调整
        battery_units.append({
            'battery_id': cell_idx + 1,  # 电池ID从1开始
            'num_cycles': num_cycles,
            'voltage': (cell_features[:, 0] if cell_features.shape[1] > 0
                        else np.zeros(num_cycles)),
            'current': (cell_features[:, 1] if cell_features.shape[1] > 1
                        else np.zeros(num_cycles)),
            'temperature': (cell_features[:, 2]
                            if cell_features.shape[1] > 2
                            else np.zeros(num_cycles)),
            'capacity': (cell_features[:, 3] if cell_features.shape[1] > 3
                         else np.zeros(num_cycles)),
            'resistance': (cell_features[:, 4]
                           if cell_features.shape[1] > 4
                           else np.zeros(num_cycles)),
            'soc': (cell_features[:, 5] if cell_features.shape[1] > 5
                    else np.zeros(num_cycles)),
            'soh': (cell_features[:, 6] if cell_features.shape[1] > 6
                    else np.zeros(num_cycles)),
            'power': (cell_features[:, 7] if cell_features.shape[1] > 7
                      else np.zeros(num_cycles)),
            'rul': cell_rul.flatten(),
            'pcl': cell_pcl.flatten(),
            'cycles': cell_cycles.flatten()
        })
        
        current_idx = end_idx
    
    print(f"✓ 成功组织 {len(battery_units)} 个电池单元的数据")
    return battery_units

# ========================================
# 更新电池基本信息
# ========================================


def update_battery_info(connection, battery_units):
    """更新电池基本信息表中的total_cycles"""
    print("\n正在更新电池基本信息...")
    cursor = connection.cursor()
    
    try:
        for unit in tqdm(battery_units, desc="更新电池信息"):
            battery_id = unit['battery_id']
            total_cycles = unit['num_cycles']
            
            sql = """
                UPDATE battery_info 
                SET total_cycles = %s 
                WHERE battery_id = %s
            """
            cursor.execute(sql, (total_cycles, battery_id))
        
        connection.commit()
        print(f"✓ 成功更新 {len(battery_units)} 组电池的基本信息")
        
    except Exception as e:
        connection.rollback()
        print(f"✗ 更新电池信息失败: {e}")
        raise
    finally:
        cursor.close()

# ========================================
# 导入生命周期数据
# ========================================


def import_lifecycle_data(connection, battery_units, batch_size=1000):
    """批量导入电池生命周期数据"""
    print("\n正在导入电池生命周期数据...")
    cursor = connection.cursor()
    
    # 检查表是否为空
    cursor.execute("SELECT COUNT(*) FROM battery_lifecycle_data")
    existing_count = cursor.fetchone()[0]
    
    if existing_count > 0:
        print(f"警告: 数据表中已存在 {existing_count} 条数据")
        response = input("是否清空现有数据后重新导入? (yes/no): ")
        if response.lower() == 'yes':
            cursor.execute("TRUNCATE TABLE battery_lifecycle_data")
            connection.commit()
            print("✓ 已清空现有数据")
        else:
            print("取消导入")
            return
    
    sql = """
        INSERT INTO battery_lifecycle_data 
        (battery_id, cycle_count, voltage, current, temperature, capacity, 
         resistance, soc, soh, power, rul, pcl, test_timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    total_records = 0
    batch_data = []
    
    try:
        for unit in tqdm(battery_units, desc="导入进度"):
            battery_id = unit['battery_id']
            num_cycles = unit['num_cycles']
            
            for cycle_idx in range(num_cycles):
                record = (
                    battery_id,
                    int(unit['cycles'][cycle_idx]),
                    float(unit['voltage'][cycle_idx]),
                    float(unit['current'][cycle_idx]),
                    float(unit['temperature'][cycle_idx]),
                    float(unit['capacity'][cycle_idx]),
                    float(unit['resistance'][cycle_idx]),
                    float(unit['soc'][cycle_idx]),
                    float(unit['soh'][cycle_idx]),
                    float(unit['power'][cycle_idx]),
                    int(unit['rul'][cycle_idx]),
                    float(unit['pcl'][cycle_idx]),
                    datetime.now()
                )
                batch_data.append(record)
                
                # 批量插入
                if len(batch_data) >= batch_size:
                    cursor.executemany(sql, batch_data)
                    connection.commit()
                    total_records += len(batch_data)
                    batch_data = []
        
        # 插入剩余数据
        if batch_data:
            cursor.executemany(sql, batch_data)
            connection.commit()
            total_records += len(batch_data)
        
        print(f"✓ 成功导入 {total_records} 条生命周期数据")
        
    except Exception as e:
        connection.rollback()
        print(f"✗ 导入生命周期数据失败: {e}")
        raise
    finally:
        cursor.close()

# ========================================
# 更新统计信息
# ========================================


def update_statistics(connection, battery_units):
    """调用存储过程更新统计信息"""
    print("\n正在更新统计信息...")
    cursor = connection.cursor()
    
    try:
        for unit in tqdm(battery_units, desc="更新统计"):
            battery_id = unit['battery_id']
            cursor.callproc('update_battery_statistics', [battery_id])
        
        connection.commit()
        print(f"✓ 成功更新 {len(battery_units)} 组电池的统计信息")
        
    except Exception as e:
        connection.rollback()
        print(f"✗ 更新统计信息失败: {e}")
        raise
    finally:
        cursor.close()

# ========================================
# 验证导入结果
# ========================================


def verify_import(connection):
    """验证数据导入结果"""
    print("\n正在验证导入结果...")
    cursor = connection.cursor()
    
    try:
        # 检查电池信息
        cursor.execute(
            "SELECT COUNT(*), dataset_type "
            "FROM battery_info GROUP BY dataset_type"
        )
        results = cursor.fetchall()
        print("\n电池信息统计:")
        for count, dataset_type in results:
            print(f"  - {dataset_type}: {count}组")
        
        # 检查生命周期数据
        cursor.execute("SELECT COUNT(*) FROM battery_lifecycle_data")
        lifecycle_count = cursor.fetchone()[0]
        print(f"\n生命周期数据总数: {lifecycle_count:,} 条")
        
        # 检查统计信息
        cursor.execute("SELECT COUNT(*) FROM data_statistics")
        stats_count = cursor.fetchone()[0]
        print(f"统计信息记录数: {stats_count} 组")
        
        # 抽样检查
        cursor.execute("""
            SELECT battery_id, COUNT(*) as cycle_count,
                   MIN(cycle_count) as min_cycle,
                   MAX(cycle_count) as max_cycle,
                   AVG(soh) as avg_soh
            FROM battery_lifecycle_data
            WHERE battery_id IN (1, 50, 100, 124)
            GROUP BY battery_id
        """)
        print("\n抽样检查 (电池 #1, #50, #100, #124):")
        print(f"{'电池ID':<10} {'数据条数':<12} {'循环范围':<20} {'平均SOH':<10}")
        print("-" * 60)
        for row in cursor.fetchall():
            battery_id, count, min_c, max_c, avg_soh = row
            cycle_range = f"{min_c}-{max_c}"
            print(f"{battery_id:<10} {count:<12} "
                  f"{cycle_range:<20} {avg_soh:.2f}")
        
        print("\n✓ 数据导入验证完成")
        
    except Exception as e:
        print(f"✗ 验证失败: {e}")
    finally:
        cursor.close()

# ========================================
# 主函数
# ========================================


def main():
    """主函数"""
    print("="*60)
    print("电池数据导入MySQL工具")
    print("="*60)
    
    # 1. 加载MAT文件
    mat_data = load_mat_data(MAT_FILE_PATH)
    
    # 2. 解析电池数据
    battery_data = parse_battery_data(mat_data)
    
    # 3. 组织电池单元数据
    battery_units = organize_battery_units(battery_data)
    
    # 4. 连接数据库
    connection = create_connection()
    
    try:
        # 5. 更新电池基本信息
        update_battery_info(connection, battery_units)
        
        # 6. 导入生命周期数据
        import_lifecycle_data(connection, battery_units)
        
        # 7. 更新统计信息
        update_statistics(connection, battery_units)
        
        # 8. 验证导入结果
        verify_import(connection)
        
        print("\n" + "="*60)
        print("✓ 数据导入完成!")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ 导入过程中发生错误: {e}")
        sys.exit(1)
    finally:
        connection.close()
        print("\n数据库连接已关闭")


if __name__ == "__main__":
    main()
