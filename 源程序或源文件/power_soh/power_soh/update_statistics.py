#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
更新统计信息（临时关闭ONLY_FULL_GROUP_BY模式）
"""

import pymysql
from tqdm import tqdm

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '092155',
    'database': 'battery_soh_db',
    'charset': 'utf8mb4'
}


def update_statistics():
    """更新所有电池的统计信息"""
    print("="*60)
    print("更新电池统计信息")
    print("="*60)
    
    # 连接数据库
    print("\n正在连接数据库...")
    try:
        connection = pymysql.connect(**DB_CONFIG)
        print("✓ 数据库连接成功")
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        return
    
    cursor = connection.cursor()
    
    try:
        # 1. 查看当前sql_mode
        print("\n查看当前SQL模式...")
        cursor.execute("SELECT @@sql_mode")
        current_mode = cursor.fetchone()[0]
        print(f"当前模式: {current_mode}")
        
        # 2. 临时关闭ONLY_FULL_GROUP_BY
        print("\n临时关闭ONLY_FULL_GROUP_BY模式...")
        new_mode = current_mode.replace('ONLY_FULL_GROUP_BY,', '')
        new_mode = new_mode.replace(',ONLY_FULL_GROUP_BY', '')
        new_mode = new_mode.replace('ONLY_FULL_GROUP_BY', '')
        cursor.execute(f"SET SESSION sql_mode = '{new_mode}'")
        print("✓ ONLY_FULL_GROUP_BY模式已临时关闭")
        
        # 3. 获取所有电池ID
        cursor.execute(
            "SELECT battery_id FROM battery_info ORDER BY battery_id"
        )
        battery_ids = [row[0] for row in cursor.fetchall()]
        print(f"\n找到 {len(battery_ids)} 组电池")
        
        # 4. 更新每个电池的统计信息
        print("\n开始更新统计信息...")
        success_count = 0
        
        for battery_id in tqdm(battery_ids, desc="更新进度"):
            try:
                cursor.callproc('update_battery_statistics', [battery_id])
                connection.commit()
                success_count += 1
            except Exception as e:
                print(f"\n✗ 电池#{battery_id}更新失败: {e}")
        
        print(f"\n✓ 成功更新 {success_count}/{len(battery_ids)} 组电池的统计信息")
        
        # 5. 验证统计结果
        print("\n验证统计结果...")
        cursor.execute("SELECT COUNT(*) FROM data_statistics")
        stats_count = cursor.fetchone()[0]
        print(f"统计记录数: {stats_count}")
        
        # 抽样检查
        cursor.execute("""
            SELECT battery_id, voltage_mean, temperature_mean, 
                   soh_mean, rul_mean, total_cycles
            FROM data_statistics 
            WHERE battery_id IN (1, 50, 100, 124)
            ORDER BY battery_id
        """)
        
        print("\n抽样检查（电池#1, #50, #100, #124）:")
        print(f"{'电池ID':<8} {'电压均值':<12} {'温度均值':<12} "
              f"{'SOH均值':<12} {'RUL均值':<12} {'总循环':<8}")
        print("-" * 70)
        
        for row in cursor.fetchall():
            battery_id, v_mean, t_mean, soh_mean, rul_mean, cycles = row
            print(f"{battery_id:<8} {v_mean:<12.4f} {t_mean:<12.2f} "
                  f"{soh_mean:<12.2f} {rul_mean:<12.2f} {cycles:<8}")
        
        print("\n" + "="*60)
        print("✓ 统计信息更新完成！")
        print("="*60)
        
        # 6. 恢复sql_mode（连接关闭后自动恢复，这里只是演示）
        print("\n注意: sql_mode的修改只在当前会话有效")
        print("重新连接后会自动恢复原来的设置")
        
    except Exception as e:
        connection.rollback()
        print(f"\n✗ 更新过程中发生错误: {e}")
    finally:
        cursor.close()
        connection.close()
        print("\n数据库连接已关闭")


if __name__ == "__main__":
    update_statistics()
