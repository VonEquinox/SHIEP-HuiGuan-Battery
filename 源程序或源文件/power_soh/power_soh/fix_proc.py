import pymysql

conn = pymysql.connect(
    host='localhost',
    user='root',
    password='092155',
    database='battery_soh_db'
)

cursor = conn.cursor()

# 读取SQL文件
with open('fix_procedure.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

# 移除DELIMITER命令，提取CREATE PROCEDURE语句
sql = sql.replace('DELIMITER //', '').replace('DELIMITER ;', '')
sql = sql.replace('//', '').strip()

try:
    cursor.execute(sql)
    conn.commit()
    print('✓ 存储过程创建成功')
except Exception as e:
    print(f'✗ 创建失败: {e}')
finally:
    cursor.close()
    conn.close()
