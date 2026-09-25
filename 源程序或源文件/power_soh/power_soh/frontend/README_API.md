# 前端API连接说明

## 后端API地址

默认后端API地址：`http://localhost:5000/api`

## 配置说明

### 1. API基础配置

API基础URL在 `src/utils/request.js` 中配置：

```javascript
const service = axios.create({
  baseURL: 'http://localhost:5000/api',
  timeout: 15000
})
```

### 2. 代理配置（可选）

如果遇到CORS问题，可以在 `vite.config.js` 中使用代理：

```javascript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:5000',
      changeOrigin: true,
      secure: false,
    }
  }
}
```

## API接口列表

所有API接口定义在 `src/api/index.js` 中：

### 认证相关
- `POST /auth/register` - 用户注册
- `POST /auth/login` - 用户登录
- `POST /auth/refresh` - 刷新token

### 用户相关
- `GET /users` - 获取用户列表
- `GET /users/:id` - 获取用户详情
- `PUT /users/:id` - 更新用户信息
- `DELETE /users/:id` - 删除用户

### 电池相关
- `GET /batteries` - 获取电池列表
- `GET /batteries/:id` - 获取电池详情
- `GET /batteries/:id/lifecycle-data` - 获取电池生命周期数据
- `GET /batteries/:id/statistics` - 获取电池统计数据

### 模型相关
- `GET /models` - 获取模型列表
- `GET /models/:id` - 获取模型详情
- `POST /models` - 创建模型
- `PUT /models/:id` - 更新模型
- `DELETE /models/:id` - 删除模型

### 训练相关
- `GET /training` - 获取训练记录列表
- `GET /training/:id` - 获取训练记录详情
- `POST /training` - 创建训练任务
- `PUT /training/:id` - 更新训练任务
- `DELETE /training/:id` - 删除训练任务

### 预测相关
- `GET /prediction` - 获取预测记录列表
- `GET /prediction/:id` - 获取预测记录详情
- `POST /prediction` - 创建预测任务
- `PUT /prediction/:id` - 更新预测结果
- `DELETE /prediction/:id` - 删除预测记录

### 数据集相关
- `GET /datasets` - 获取数据集列表
- `GET /datasets/:id` - 获取数据集详情
- `POST /datasets` - 创建数据集
- `PUT /datasets/:id` - 更新数据集
- `DELETE /datasets/:id` - 删除数据集

### 模型比较相关
- `GET /model-comparison` - 获取模型比较列表
- `GET /model-comparison/:id` - 获取模型比较详情
- `POST /model-comparison` - 创建模型比较
- `DELETE /model-comparison/:id` - 删除模型比较

## 认证机制

前端使用JWT Token进行认证：

1. 登录成功后，后端返回 `access_token` 和 `refresh_token`
2. Token存储在 `localStorage` 中
3. 每次请求自动在请求头中添加 `Authorization: Bearer <token>`
4. Token过期时（401错误），自动跳转到登录页

## 使用示例

```javascript
import { getBatteries, getBattery } from '@/api'

// 获取电池列表
const batteries = await getBatteries({ 
  dataset_type: 'train',
  skip: 0,
  limit: 10 
})

// 获取电池详情
const battery = await getBattery(1)
```

## 注意事项

1. 确保后端服务运行在 `http://localhost:5000`
2. 后端已配置CORS，允许前端跨域请求
3. 所有需要认证的接口都需要在请求头中携带Token
4. Token过期时会自动跳转到登录页
