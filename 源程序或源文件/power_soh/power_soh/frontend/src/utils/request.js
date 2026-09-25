import axios from 'axios';
import { ElMessage } from 'element-plus';
import { logout } from './auth';

// 创建axios实例
const service = axios.create({
  baseURL: '/api', // FastAPI后端地址前缀
  timeout: 60000 // 请求超时时间
});

// 请求拦截器
service.interceptors.request.use(
  config => {
    
    // ================= 🪄 核心魔术修复区 =================
    // 1. 修复双重 /api/api 问题（自动去除前端多写的 /api）
    if (config.url && config.url.startsWith('/api/')) {
      config.url = config.url.substring(4); // 把 '/api/xxx' 变成 '/xxx'
    }

    // 2. 自动修正前后端不一致的 URL 拼写
    if (config.url) {
      // 前端写的是 /predictions，后端是 /prediction/
      if (config.url.includes('/predictions')) {
        config.url = config.url.replace('/predictions', '/prediction/');
      }
      // 前端写的是 /carbon_calculation/total，后端是 /carbon/total
      if (config.url.includes('/carbon_calculation/total')) {
        config.url = config.url.replace('/carbon_calculation/total', '/carbon/total');
      }
    }
    // ====================================================

    // 从 localStorage 获取 token
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  error => {
    console.error('请求错误:', error);
    return Promise.reject(error);
  }
);

// 响应拦截器
service.interceptors.response.use(
  response => {
    // 直接返回响应，让业务代码处理数据
    return response;
  },
  error => {
    console.error('响应错误:', error);
    
    if (error.response) {
      const { status, data } = error.response;
      
      // 401 未授权
      if (status === 401) {
        ElMessage.error('登录已过期，请重新登录');
        logout(); 
        if (window.location.pathname !== '/login') {
          window.location.href = '/#/login';
        }
      } 
      // 403 禁止访问
      else if (status === 403) {
        ElMessage.error('权限不足，无法访问此资源');
      } 
      // 422 验证错误
      else if (status === 422) {
        const detail = data.detail;
        if (Array.isArray(detail)) {
          ElMessage.error(detail[0]?.msg || '请求参数错误');
        } else {
          ElMessage.error(detail || '请求参数错误');
        }
      }
      // 其他错误
      else {
        ElMessage.error(data.detail || data.message || `请求失败: ${status}`);
      }
    } else {
      ElMessage.error('网络错误，请检查网络连接');
    }
    
    return Promise.reject(error);
  }
);

export default service;