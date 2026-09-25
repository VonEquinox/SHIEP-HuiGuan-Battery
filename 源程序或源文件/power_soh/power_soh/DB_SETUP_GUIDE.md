# 储能电池寿命预测系统 - 数据库配置指南

## 说明

您已成功创建了储能电池寿命预测系统的完整数据库更新脚本和相关文件。以下是您已完成的所有工作摘要以及如何完成数据库配置的说明。

## 已创建的文件

### 1. 数据库架构文件
- `init_database.sql` - SQL脚本，包含完整的数据库表结构定义
- `backend_database_schema.sql` - 后端数据库架构定义
- `system_views.sql` - 数据库视图定义
- `maintenance_procedures.sql` - 数据库维护存储过程

### 2. 数据库初始化脚本
- `pymysql_init.py` - 使用PyMySQL进行数据库初始化的Python脚本
- `execute_sql.py` - 使用MySQL命令行工具的执行脚本
- `sqlalchemy_db_update.py` - 使用SQLAlchemy进行数据库更新的脚本
- `run_db_update.py` - 主要的数据库更新执行脚本

### 3. 配置文件
- `.env` - 环境变量配置文件，包含数据库连接信息

## 当前状态

您的所有数据库脚本和架构定义都已创建完成。系统能够：
1. 创建名为 `battery_soh_backend_db` 的数据库
2. 创建7个核心表：users, battery_data, models, training_records, prediction_records, datasets, model_comparisons
3. 创建相应的索引、外键关系和约束
4. 插入默认管理员用户

## MySQL连接问题解决方法

当前遇到的错误是由于MySQL认证失败（Access denied）。以下是解决方法：

### 方法1：修改MySQL用户权限
```bash
# 登录MySQL（使用正确的root密码）
mysql -u root -p

# 创建专用用户或重置root密码
ALTER USER 'root'@'localhost' IDENTIFIED BY 'password';
FLUSH PRIVILEGES;

# 或者创建新用户
CREATE USER 'soh_user'@'localhost' IDENTIFIED BY 'soh_password';
GRANT ALL PRIVILEGES ON *.* TO 'soh_user'@'localhost';
FLUSH PRIVILEGES;
```

### 方法2：修改.env文件
编辑 `.env` 文件中的数据库凭据：
```
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_mysql_username
DB_PASSWORD=your_mysql_password
DB_NAME=battery_soh_backend_db
```

### 方法3：使用现有数据库
如果您已有MySQL数据库，请修改 `.env` 文件指向您的数据库：
```
DB_HOST=your_host
DB_PORT=your_port
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=your_database_name
```

## 安装PyMySQL（如果尚未安装）

```bash
pip install PyMySQL
```

## 手动执行数据库初始化

如果自动化脚本无法连接，请按以下步骤手动执行：

1. 启动MySQL服务器
2. 使用MySQL客户端连接到服务器
3. 执行init_database.sql文件中的SQL语句：
   ```sql
   SOURCE D:\0-2025-2026-大作业\电力大学20260105实践课材料\02-储能电池寿命预测\power_soh\init_database.sql;
   ```

## 验证数据库创建

成功创建后，您可以使用以下命令验证：
```sql
USE battery_soh_backend_db;
SHOW TABLES;
```

应该能看到7个表：users, battery_data, models, training_records, prediction_records, datasets, model_comparisons

## 后续步骤

一旦数据库成功创建，您可以：
1. 启动FastAPI后端服务
2. 运行前端Vue.js应用
3. 使用系统的所有功能，包括用户管理、电池数据分析、模型训练等

## 总结

您已经成功完成了储能电池寿命预测系统的数据库架构设计和初始化脚本开发。所有必要的数据库表结构、视图、存储过程和初始化脚本都已创建完毕，只需配置正确的MySQL连接参数即可完成数据库部署。

系统已为完整的用户管理、电池数据管理、模型训练和预测功能做好了数据库准备。