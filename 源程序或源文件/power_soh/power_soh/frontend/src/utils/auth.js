/**
 * 认证相关工具函数
 */

// 检查用户是否已登录
export const isAuthenticated = () => {
  const token = localStorage.getItem('token')
  return !!token
}

// 获取用户信息
export const getUserInfo = () => {
  const userInfo = localStorage.getItem('userInfo')
  return userInfo ? JSON.parse(userInfo) : null
}

// 获取用户状态
export const getUserStatus = () => {
  const userInfo = getUserInfo()
  return userInfo?.status || false
}

// 检查用户是否活跃
export const isUserActive = () => {
  return getUserStatus() === true
}

// 登出
export const logout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')
}

// 设置认证头
export const setAuthHeader = (config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
}