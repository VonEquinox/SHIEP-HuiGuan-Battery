# CORS问题修复指南

## 问题描述
前端访问后端API时出现CORS错误：
```
Access to XMLHttpRequest at 'http://localhost:5000/api/...' from origin 'http://localhost:3000' 
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present
```

## 已修复的问题

### 1. CORS配置更新 (`backend/main.py`)
- ✅ 已配置CORS中间件，允许来自 `http://localhost:3000` 的请求
- ✅ 允许所有HTTP方法（GET, POST, PUT, DELETE, OPTIONS等）
- ✅ 允许所有请求头和响应头
- ✅ 添加了全局异常处理

### 2. API路径修复
- ✅ `/api/batteries` 现在同时支持 `/api/batteries` 和 `/api/batteries/`
- ✅ `/api/batteries/{id}/lifecycle-data` 同时支持 `/api/batteries/{id}/lifecycle`
- ✅ 添加了参数兼容性（支持 `page/page_size` 和 `skip/limit`）

### 3. 前端API调用修复
- ✅ 修复了数据格式解析（后端直接返回数据，没有 `success` 字段）
- ✅ 修复了统计信息API路径
- ✅ 修复了生命周期数据API路径

## 解决步骤

### 步骤1: 重启后端服务
```bash
# 停止当前运行的后端服务（Ctrl+C）
# 然后重新启动
cd backend
python main.py
```

### 步骤2: 清除浏览器缓存
1. 打开浏览器开发者工具（F12）
2. 右键点击刷新按钮
3. 选择"清空缓存并硬性重新加载"

或者：
```javascript
// 在浏览器控制台执行
localStorage.clear()
location.reload()
```

### 步骤3: 验证CORS配置
访问 `http://localhost:5000/health` 应该返回：
```json
{"status": "healthy", "version": "1.0.0"}
```

检查响应头应该包含：
- `Access-Control-Allow-Origin: http://localhost:3000`
- `Access-Control-Allow-Methods: *`
- `Access-Control-Allow-Headers: *`

## 如果问题仍然存在

### 检查1: 后端服务是否运行
```bash
# 检查端口5000是否被占用
netstat -ano | findstr :5000
```

### 检查2: 数据库连接
确保MySQL服务正在运行，并且数据库 `battery_soh_db` 已创建。

### 检查3: 查看后端日志
启动后端时应该看到：
```
INFO:     Uvicorn running on http://0.0.0.0:5000
```

如果有错误，请检查：
- 数据库连接是否正常
- 依赖包是否已安装：`pip install -r backend/requirements.txt`

### 检查4: 使用代理（临时方案）
如果CORS仍然有问题，可以在 `frontend/vite.config.js` 中使用代理：
```javascript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:5000',
      changeOrigin: true,
    }
  }
}
```

## 常见错误及解决方案

### 错误1: 404 Not Found
- 检查API路径是否正确
- 确保后端路由已正确注册

### 错误2: 422 Unprocessable Entity
- 检查请求参数格式
- 查看后端日志了解具体验证错误

### 错误3: 500 Internal Server Error
- 检查数据库连接
- 查看后端日志了解具体错误
- 确保数据库表已创建

### 错误4: 401 Unauthorized
- 检查token是否有效
- 确保登录后token已正确存储

## 测试API连接

### 使用curl测试：
```bash
# 测试健康检查
curl http://localhost:5000/health

# 测试CORS
curl -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" \
     -X OPTIONS \
     http://localhost:5000/api/batteries
```

### 使用浏览器测试：
打开 `http://localhost:5000/docs` 查看API文档（Swagger UI）

## 注意事项

1. **开发环境**：当前CORS配置允许 `localhost:3000`，生产环境需要修改为实际域名
2. **数据库**：确保MySQL服务运行，数据库已创建
3. **端口冲突**：确保5000端口未被其他服务占用
4. **依赖安装**：确保所有Python依赖已安装
