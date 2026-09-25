// API 接口定义
// 用于与后端FastAPI服务进行交互
import request from '@/utils/request'

// ==================== 认证相关 ====================
// 用户注册
export const register = (data) => {
  return request.post('/auth/register', data)
}

// 用户登录
export const login = (data) => {
  return request.post('/auth/login', data)
}

// 刷新token
export const refreshToken = (refreshToken) => {
  return request.post('/auth/refresh', { refresh_token: refreshToken })
}

// ==================== 用户相关 ====================
// 获取用户列表 (已修复：添加斜杠)
export const getUsers = (params = {}) => {
  return request.get('/users/', { params })
}

// 获取用户信息
export const getUser = (userId) => {
  return request.get(`/users/${userId}`)
}

// 更新用户信息
export const updateUser = (userId, data) => {
  return request.put(`/users/${userId}`, data)
}

// 删除用户
export const deleteUser = (userId) => {
  return request.delete(`/users/${userId}`)
}

// ==================== 电池相关 ====================
// 获取电池列表 (已修复：添加斜杠)
export const getBatteries = (params = {}) => {
  return request.get('/batteries/', { params })
}

// 获取电池详情
export const getBattery = (batteryId) => {
  return request.get(`/batteries/${batteryId}`)
}

// 获取电池生命周期数据
export const getBatteryLifecycleData = (batteryId, params = {}) => {
  return request.get(`/batteries/${batteryId}/lifecycle-data`, { params })
}

// 获取电池统计数据
export const getBatteryStatistics = (batteryId) => {
  return request.get(`/batteries/${batteryId}/statistics`)
}

// ==================== 模型相关 ====================
// 获取模型列表 (已修复：添加斜杠，解决 403 Forbidden 报错)
export const getModels = (params = {}) => {
  return request.get('/models/', { params })
}

// 获取模型详情
export const getModel = (modelId) => {
  return request.get(`/models/${modelId}`)
}

// 创建模型 (已修复：添加斜杠)
export const createModel = (data) => {
  return request.post('/models/', data)
}

// 更新模型
export const updateModel = (modelId, data) => {
  return request.put(`/models/${modelId}`, data)
}

// 删除模型
export const deleteModel = (modelId) => {
  return request.delete(`/models/${modelId}`)
}

// ==================== 训练相关 ====================
// 获取训练记录列表 (已修复：添加斜杠)
export const getTrainingRecords = (params = {}) => {
  return request.get('/training/', { params })
}

// 获取训练记录详情
export const getTrainingRecord = (recordId) => {
  return request.get(`/training/${recordId}`)
}

// 创建训练任务 (已修复：添加斜杠)
export const createTrainingTask = (data) => {
  return request.post('/training/', data)
}

// 更新训练任务
export const updateTrainingTask = (taskId, data) => {
  return request.put(`/training/${taskId}`, data)
}

// 删除训练任务
export const deleteTrainingTask = (taskId) => {
  return request.delete(`/training/${taskId}`)
}

// ==================== 预测相关 ====================
// 获取预测记录列表 (已修复：添加斜杠)
export const getPredictions = (params = {}) => {
  return request.get('/prediction/', { params })
}

// 获取预测记录详情
export const getPrediction = (predictionId) => {
  return request.get(`/prediction/${predictionId}`)
}

// 创建预测任务 (已修复：添加斜杠)
export const createPrediction = (data) => {
  return request.post('/prediction/', data)
}

// 更新预测结果
export const updatePrediction = (predictionId, data) => {
  return request.put(`/prediction/${predictionId}`, data)
}

// 删除预测记录
export const deletePrediction = (predictionId) => {
  return request.delete(`/prediction/${predictionId}`)
}

// 获取预测记录详情（包含建议的实际SOH值）
export const getPredictionDetail = (predictionId) => {
  return request.get(`/prediction/${predictionId}`)
}

// 更新预测记录的实际值
export const updatePredictionActualValue = (predictionId, data) => {
  return request.put(`/prediction/${predictionId}/actual-value`, data)
}

// ==================== 数据集相关 ====================
// 获取数据集列表 (已修复：添加斜杠)
export const getDatasets = (params = {}) => {
  return request.get('/datasets/', { params })
}

// 获取数据集详情
export const getDataset = (datasetId) => {
  return request.get(`/datasets/${datasetId}`)
}

// 创建数据集 (已修复：添加斜杠)
export const createDataset = (data) => {
  return request.post('/datasets/', data)
}

// 更新数据集
export const updateDataset = (datasetId, data) => {
  return request.put(`/datasets/${datasetId}`, data)
}

// 删除数据集
export const deleteDataset = (datasetId) => {
  return request.delete(`/datasets/${datasetId}`)
}

// ==================== 模型比较相关 ====================
// 获取模型比较列表 (已修复：添加斜杠)
export const getModelComparisons = (params = {}) => {
  return request.get('/model-comparison/', { params })
}

// 获取模型比较详情
export const getModelComparison = (comparisonId) => {
  return request.get(`/model-comparison/${comparisonId}`)
}

// 创建模型比较 (已修复：添加斜杠)
export const createModelComparison = (data) => {
  return request.post('/model-comparison/', data)
}

// 删除模型比较
export const deleteModelComparison = (comparisonId) => {
  return request.delete(`/model-comparison/${comparisonId}`)
}

// 获取性能统计数据（用于结果分析）
export const getPerformanceStatistics = () => {
  return request.get('/model-comparison/analysis/performance-statistics')
}

// 获取预测误差分布（结果分析页）
export const getErrorDistribution = (params = {}) => {
  return request.get('/model-comparison/analysis/error-distribution', { params })
}

// 获取模型收敛数据
export const getConvergenceData = (modelId) => {
  return request.get(`/model-comparison/analysis/convergence-data/${modelId}`)
}

// ==================== 仪表盘相关 ====================
// 获取仪表盘统计数据
export const getDashboardStatistics = () => {
  return request.get('/dashboard/statistics')
}

// ==================== 资源共享相关 ====================
// 创建分享 (已修复：添加斜杠，解决 403 Forbidden 报错)
export const createShare = (data) => {
  return request.post('/shares/', data)
}

// 获取我分享出去的资源列表 (已修复：添加斜杠，解决 403 Forbidden 报错)
export const getMyShares = (params = {}) => {
  return request.get('/shares/', { params })
}

// 获取我被分享的资源列表
export const getReceivedShares = (params = {}) => {
  return request.get('/shares/received', { params })
}

// 删除分享
export const deleteShare = (shareId) => {
  return request.delete(`/shares/${shareId}`)
}

// 检查资源权限
export const checkPermission = (resourceType, resourceId) => {
  return request.get('/shares/check-permission', {
    params: { resource_type: resourceType, resource_id: resourceId }
  })
}

// ==================== 工单相关 ====================
// 获取工单列表
export const getWorkOrders = () => {
  return request.get('/work_orders')
}

// 获取分配给特定用户的工单
export const getAssignedWorkOrders = (userId) => {
  return request.get(`/work_orders/assigned/${userId}`)
}

// 分配工单给用户
export const assignWorkOrder = (orderId, userId) => {
  return request.post(`/work_orders/${orderId}/assign`, { user_id: userId })
}

// 闭环工单
export const resolveWorkOrder = (orderId, notes, imageUrl) => {
  return request.post(`/work_orders/${orderId}/resolve`, { notes, image_url: imageUrl })
}

// ==================== 智能派单调度相关 ====================
// 调用后端 AI 算法获取推荐人员列表
export const getRecommendedWorkers = (orderId) => {
  return request.get(`/work_orders/${orderId}/recommend`)
}