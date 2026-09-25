#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一数据库创建脚本
根据 unified_database_schema.sql, unified_stored_procedures.sql, unified_views.sql
创建完整的数据库结构
"""

import pymysql
import sys
import os
from pathlib import Path

# 设置Windows控制台编码为UTF-8
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except:
        pass

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '092155',
    'charset': 'utf8mb4'
}

# SQL文件列表（按执行顺序）
SQL_FILES = [
    'unified_database_schema.sql',
    'unified_stored_procedures.sql',
    'unified_views.sql'
]


def split_sql_statements(sql_content):
    """
    分割SQL语句，正确处理DELIMITER
    """
    statements = []
    current_statement = []
    delimiter = ';'
    in_delimiter_block = False
    
    lines = sql_content.split('\n')
    
    for i, line in enumerate(lines):
        original_line = line
        line = line.strip()
        
        # 跳过空行和注释行
        if not line or line.startswith('--'):
            continue
        
        # 处理DELIMITER命令
        if line.upper().startswith('DELIMITER'):
            parts = line.split()
            if len(parts) > 1:
                new_delimiter = parts[1]
                if new_delimiter == '//':
                    delimiter = '//'
                    in_delimiter_block = True
                elif new_delimiter == ';':
                    delimiter = ';'
                    in_delimiter_block = False
            continue
        
        # 添加到当前语句
        current_statement.append(original_line)
        
        # 检查是否到达语句结束
        if line.endswith(delimiter):
            stmt = '\n'.join(current_statement)
            # 移除末尾的分隔符
            if delimiter == '//':
                stmt = stmt.rstrip().rstrip('//').strip()
            else:
                stmt = stmt.rstrip().rstrip(';').strip()
            
            if stmt:
                statements.append(stmt)
            current_statement = []
    
    # 处理最后可能剩余的语句
    if current_statement:
        stmt = '\n'.join(current_statement).strip()
        if stmt and not stmt.endswith('DELIMITER'):
            statements.append(stmt)
    
    return statements


def execute_sql_file(connection, sql_file_path, file_index, total_files):
    """执行单个SQL文件"""
    sql_file = Path(sql_file_path)
    
    if not sql_file.exists():
        print(f"[ERROR] SQL文件不存在: {sql_file_path}")
        return False
    
    print(f"\n{'='*60}")
    print(f"[{file_index}/{total_files}] 执行文件: {sql_file.name}")
    print(f"{'='*60}")
    
    try:
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        print(f"[OK] SQL文件读取成功 ({len(sql_content)} 字符)")
    except Exception as e:
        print(f"[ERROR] 读取SQL文件失败: {e}")
        return False
    
    # 分割SQL语句
    statements = split_sql_statements(sql_content)
    print(f"[OK] 解析到 {len(statements)} 条SQL语句")
    
    cursor = connection.cursor()
    executed = 0
    errors = 0
    
    try:
        for idx, stmt in enumerate(statements, 1):
            stmt = stmt.strip()
            if not stmt:
                continue
            
            try:
                # 处理USE语句
                if stmt.upper().startswith('USE '):
                    db_name = stmt.split()[1].strip('`;')
                    connection.select_db(db_name)
                    print(f"  [{idx}] 切换到数据库: {db_name}")
                    executed += 1
                    continue
                
                # 处理SELECT语句（用于显示信息）
                if stmt.upper().startswith('SELECT '):
                    if 'AS message' in stmt or 'AS battery_count' in stmt:
                        cursor.execute(stmt)
                        result = cursor.fetchone()
                        if result:
                            print(f"  [{idx}] {result[0]}")
                    executed += 1
                    continue
                
                # 执行SQL语句
                cursor.execute(stmt)
                executed += 1
                
                # 显示关键操作
                stmt_upper = stmt.upper()
                if 'CREATE DATABASE' in stmt_upper:
                    db_name = stmt.split('DATABASE')[1].split()[1].strip('`;')
                    print(f"  [{idx}] [OK] 创建数据库: {db_name}")
                elif 'CREATE TABLE' in stmt_upper or 'CREATE OR REPLACE TABLE' in stmt_upper:
                    # 提取表名
                    parts = stmt.split('CREATE')
                    if len(parts) > 1:
                        table_part = parts[1].split('(')[0].strip()
                        table_name = table_part.split()[1] if 'TABLE' in table_part else table_part.split()[0]
                        print(f"  [{idx}] [OK] 创建表: {table_name}")
                elif 'CREATE PROCEDURE' in stmt_upper:
                    # 提取存储过程名
                    proc_name = stmt.split('PROCEDURE')[1].split('(')[0].strip()
                    print(f"  [{idx}] [OK] 创建存储过程: {proc_name}")
                elif 'CREATE OR REPLACE VIEW' in stmt_upper or 'CREATE VIEW' in stmt_upper:
                    # 提取视图名
                    view_part = stmt.split('VIEW')[1].split()[0].strip()
                    print(f"  [{idx}] [OK] 创建视图: {view_part}")
                elif 'INSERT INTO' in stmt_upper:
                    # 只显示第一次插入
                    if executed <= 5:  # 只显示前几次
                        table_name = stmt.split('INTO')[1].split()[0].strip()
                        print(f"  [{idx}] [OK] 插入数据到: {table_name}")
                elif 'ON DUPLICATE KEY UPDATE' in stmt_upper:
                    # 批量插入，只显示一次
                    if idx == 1:
                        print(f"  [{idx}] [OK] 批量插入数据...")
                
                connection.commit()
                
            except pymysql.err.ProgrammingError as e:
                # 某些错误可以忽略（如表已存在等）
                error_msg = str(e).lower()
                if 'already exists' in error_msg or 'duplicate' in error_msg:
                    print(f"  [{idx}] [WARN] 已存在，跳过: {stmt[:50]}...")
                else:
                    print(f"  [{idx}] [ERROR] 执行失败: {stmt[:50]}...")
                    print(f"      错误: {e}")
                    errors += 1
            except Exception as e:
                error_msg = str(e).lower()
                if 'already exists' in error_msg or 'duplicate' in error_msg:
                    print(f"  [{idx}] [WARN] 已存在，跳过")
                else:
                    print(f"  [{idx}] [ERROR] 执行失败: {stmt[:50]}...")
                    print(f"      错误: {e}")
                    errors += 1
        
        print(f"\n[OK] 文件执行完成: 成功 {executed} 条, 错误 {errors} 条")
        return True
        
    except Exception as e:
        connection.rollback()
        print(f"\n[ERROR] 执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cursor.close()


def verify_database(connection):
    """验证数据库创建结果"""
    print(f"\n{'='*60}")
    print("验证数据库结构")
    print(f"{'='*60}")
    
    try:
        cursor = connection.cursor()
        
        # 切换到目标数据库
        cursor.execute("USE battery_soh_db")
        
        # 检查表
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print(f"\n[OK] 数据库表列表（共 {len(tables)} 张表）:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # 检查存储过程
        cursor.execute("SHOW PROCEDURE STATUS WHERE Db = 'battery_soh_db'")
        procedures = cursor.fetchall()
        print(f"\n[OK] 存储过程列表（共 {len(procedures)} 个）:")
        for proc in procedures:
            print(f"  - {proc[1]}")
        
        # 检查视图
        cursor.execute("SHOW FULL TABLES WHERE Table_type = 'VIEW'")
        views = cursor.fetchall()
        print(f"\n[OK] 视图列表（共 {len(views)} 个）:")
        for view in views:
            print(f"  - {view[0]}")
        
        # 检查电池信息
        cursor.execute("SELECT COUNT(*) FROM battery_info")
        battery_count = cursor.fetchone()[0]
        print(f"\n[OK] 电池基本信息: {battery_count} 组")
        
        # 检查数据集类型分布
        cursor.execute("""
            SELECT dataset_type, COUNT(*) as count 
            FROM battery_info 
            GROUP BY dataset_type
        """)
        dataset_dist = cursor.fetchall()
        print(f"\n[OK] 数据集分布:")
        for dist in dataset_dist:
            print(f"  - {dist[0]}: {dist[1]} 组")
        
        cursor.close()
        return True
        
    except Exception as e:
        print(f"\n[ERROR] 验证失败: {e}")
        return False


def main():
    """主函数"""
    print("="*60)
    print("统一数据库创建工具")
    print("="*60)
    print(f"将执行以下SQL文件:")
    for i, sql_file in enumerate(SQL_FILES, 1):
        print(f"  {i}. {sql_file}")
    print("="*60)
    
    # 连接MySQL服务器（不指定数据库）
    print("\n正在连接MySQL服务器...")
    try:
        connection = pymysql.connect(**DB_CONFIG)
        print(f"[OK] MySQL连接成功 (host: {DB_CONFIG['host']}, port: {DB_CONFIG['port']})")
    except pymysql.err.OperationalError as e:
        print(f"[ERROR] MySQL连接失败: {e}")
        print("\n可能的原因：")
        print("1. MySQL服务未启动")
        print("2. 用户名或密码错误")
        print("3. 端口配置错误")
        print("4. 防火墙阻止连接")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 连接失败: {e}")
        sys.exit(1)
    
    # 执行所有SQL文件
    success_count = 0
    for idx, sql_file in enumerate(SQL_FILES, 1):
        if execute_sql_file(connection, sql_file, idx, len(SQL_FILES)):
            success_count += 1
        else:
            print(f"\n[ERROR] 文件 {sql_file} 执行失败，继续执行其他文件...")
    
    # 验证数据库
    if success_count == len(SQL_FILES):
        verify_database(connection)
        print(f"\n{'='*60}")
        print("[OK] 数据库创建完成！")
        print(f"{'='*60}")
        print("\n下一步操作：")
        print("1. 运行数据导入脚本: python import_data_to_mysql.py")
        print("2. 或使用其他方式导入电池生命周期数据")
    else:
        print(f"\n{'='*60}")
        print(f"[WARN] 部分文件执行失败 ({success_count}/{len(SQL_FILES)})")
        print(f"{'='*60}")
    
    connection.close()
    print("\n数据库连接已关闭")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 发生未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
