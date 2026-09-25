import { createRouter, createWebHashHistory } from 'vue-router'
import { isAuthenticated } from '@/utils/auth'

const routes = [
  {
    path: '/',
    redirect: '/login'  // 默认跳转到登录页，避免空白页
  },
  // ================= 基础/算法平台相关路由 =================
  {
    path: '/test-data',
    name: 'TestData',
    component: () => import('../views/TestData.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/data',
    name: 'DataManagement',
    component: () => import('../views/DataManagement.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/train',
    name: 'TrainPlatform',
    component: () => import('../views/TrainPlatform.vue'),
    meta: { title: '算法训练平台', requiresAuth: true }
  },
  {
    path: '/test',
    name: 'TestPlatform',
    component: () => import('../views/TestPlatform.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/models',
    name: 'ModelManagement',
    component: () => import('../views/ModelManagement.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/results',
    name: 'ResultsAnalysis',
    component: () => import('../views/ResultsAnalysis.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/update-actual-value',
    name: 'UpdateActualValue',
    component: () => import('../views/UpdateActualValue.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/shares',
    name: 'ShareManagement',
    component: () => import('../views/ShareManagement.vue'),
    meta: { requiresAuth: true, title: '资源共享管理' }
  },
  {
    path: '/admin',
    name: 'AdminPanel',
    component: () => import('../views/AdminPanel.vue'),
    meta: { requiresAuth: true }
  },

  // ================= 登录注册路由 =================
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { requiresGuest: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: { requiresGuest: true }
  },

  // ================= 申报书核心：四大业务模块路由 =================
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { requiresAuth: true, title: '可视化大屏' }
  },
  { 
    path: '/cell-prediction', 
    name: 'CellPrediction', 
    component: () => import('../views/CellPrediction.vue'), 
    meta: { requiresAuth: true, title: '电芯预测与预警' } 
  },
  { 
    path: '/carbon-calculation', 
    name: 'CarbonCalculation', 
    component: () => import('../views/CarbonCalculation.vue'), 
    meta: { requiresAuth: true, title: '减碳核算' } 
  },
  { 
    // 注意：这里统一改为了单数 /work-order 以匹配 App.vue 的左侧菜单
    path: '/work-order', 
    name: 'WorkOrder', 
    component: () => import('../views/WorkOrder.vue'), 
    meta: { requiresAuth: true, title: '智能派单与预警' } 
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth)
  const requiresGuest = to.matched.some(record => record.meta.requiresGuest)
  const authenticated = isAuthenticated()

  // 动态修改页面标题 (可选，增加体验)
  if (to.meta.title) {
    document.title = `${to.meta.title} - 数智赋能平台`
  } else {
    document.title = '数智赋能多园区储能管理平台'
  }

  if (requiresAuth && !authenticated) {
    // 需要登录但未登录，跳转到登录页，并携带重定向参数
    next({ path: '/login', query: { redirect: to.fullPath } })
  } else if (requiresGuest && authenticated) {
    // 需要访客但已登录（如已登录再去访问/login），跳转到核心业务仪表板
    next({ path: '/dashboard' })
  } else {
    next()
  }
})

export default router