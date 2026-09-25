#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
初始化数据库脚本
执行database_schema.sql创建数据库和表结构
"""

import pymysql
import sys

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '092155',
    'charset': 'utf8mb4'
}


def execute_sql_file(sql_file_path):
    """执行SQL文件"""
    print(f"正在读取SQL文件: {sql_file_path}")
    
    try:
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        print("✓ SQL文件读取成功")
    except Exception as e:
        print(f"✗ 读取SQL文件失败: {e}")
        sys.exit(1)
    
    # 连接MySQL（不指定数据库）
    print("\n正在连接MySQL服务器...")
    try:
        connection = pymysql.connect(**DB_CONFIG)
        print("✓ MySQL连接成功")
    except Exception as e:
        print(f"✗ MySQL连接失败: {e}")
        print("请检查MySQL服务是否已启动以及密码是否正确")
        sys.exit(1)
    
    cursor = connection.cursor()
    
    try:
        # 分割SQL语句（按分号和DELIMITER分隔）
        statements = []
        current_statement = []
        delimiter = ';'
        
        for line in sql_content.split('\n'):
            line = line.strip()
            
            # 跳过注释和空行
            if not line or line.startswith('--'):
                continue
            
            # 处理DELIMITER命令
            if line.upper().startswith('DELIMITER'):
                if 'DELIMITER //' in line:
                    delimiter = '//'
                elif 'DELIMITER ;' in line:
                    delimiter = ';'
                continue
            
            current_statement.append(line)
            
            # 检查是否到达语句结束
            if line.endswith(delimiter):
                stmt = ' '.join(current_statement)
                if delimiter == '//':
                    stmt = stmt[:-2]  # 移除末尾的//
                else:
                    stmt = stmt[:-1]  # 移除末尾的;
                
                if stmt.strip():
                    statements.append(stmt)
                current_statement = []
        
        # 执行每条SQL语句
        print(f"\n开始执行SQL语句（共{len(statements)}条）...")
        executed = 0
        
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt:
                continue
            
            try:
                # 特殊处理USE语句
                if stmt.upper().startswith('USE '):
                    db_name = stmt.split()[1].strip('`;')
                    connection.select_db(db_name)
                    print(f"  - 切换到数据库: {db_name}")
                # 跳过SELECT语句（用于显示信息）
                elif stmt.upper().startswith('SELECT '):
                    if 'AS message' in stmt or 'AS battery_count' in stmt:
                        cursor.execute(stmt)
                        result = cursor.fetchone()
                        if result:
                            print(f"  - {result[0]}")
                    continue
                else:
                    cursor.execute(stmt)
                    executed += 1
                    
                    # 显示关键操作
                    if 'CREATE DATABASE' in stmt.upper():
                        print("  ✓ 创建数据库")
                    elif 'CREATE TABLE' in stmt.upper():
                        parts = stmt.split('CREATE TABLE')[1]
                        table_name = parts.split('(')[0].strip().split()[0]
                        print(f"✓ 创建表: {table_name}")
                    elif 'CREATE PROCEDURE' in stmt.upper():
                        print("  ✓ 创建存储过程")
                    elif 'CREATE OR REPLACE VIEW' in stmt.upper():
                        print("  ✓ 创建视图")
                    elif 'INSERT INTO battery_info' in stmt:
                        # 只显示第一次插入信息
                        if executed == 1 or '电池组 #1' in stmt:
                            print("  ✓ 插入电池基本信息...")
                
                connection.commit()
                
            except Exception as e:
                # 忽略某些无关紧要的错误
                if 'already exists' in str(e).lower():
                    continue
                print(f"  ⚠ 执行失败: {stmt[:50]}... \n     错误: {e}")
        
        print(f"\n✓ 成功执行 {executed} 条SQL语句")
        
        # 验证表是否创建成功
        cursor.execute("USE battery_soh_db")
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        print(f"\n数据库表列表（共{len(tables)}张表）:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # 检查电池信息
        cursor.execute("SELECT COUNT(*) FROM battery_info")
        battery_count = cursor.fetchone()[0]
        print(f"\n✓ 电池基本信息: {battery_count} 组")
        
        print("\n" + "="*60)
        print("✓ 数据库初始化完成！")
        print("="*60)
        print("\n现在可以运行: python import_data_to_mysql.py")
        
    except Exception as e:
        connection.rollback()
        print(f"\n✗ 执行过程中发生错误: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    print("="*60)
    print("数据库初始化工具")
    print("="*60)
    
    sql_file = './database_schema.sql'
    execute_sql_file(sql_file)
