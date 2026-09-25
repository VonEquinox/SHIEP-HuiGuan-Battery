<template>
  <el-config-provider>
    <div v-if="isAuthPage" class="auth-layout">
      <router-view />
    </div>

    <div v-else class="app-container">
      <aside class="sidebar">
        <div class="logo-box">
          <img src="/favicon.svg" alt="logo" class="logo" v-if="false" />
          <h2 class="sys-title">数智赋能平台</h2>
        </div>
        
        <el-scrollbar>
          <el-menu
            :default-active="activeMenu"
            class="el-menu-vertical"
            background-color="#1e1e2d"
            text-color="#a2a3b7"
            active-text-color="#ffffff"
            router
          >
            <el-menu-item-group title="核心业务监测">
              <el-menu-item index="/dashboard">
                <el-icon><DataBoard /></el-icon>
                <span>可视化大屏</span>
              </el-menu-item>
              <el-menu-item index="/cell-prediction">
                <el-icon><Monitor /></el-icon>
                <span>电芯预测预警</span>
              </el-menu-item>
              <el-menu-item index="/carbon-calculation">
                <el-icon><PieChart /></el-icon>
                <span>减碳核算</span>
              </el-menu-item>
              <el-menu-item index="/work-order">
                <el-icon><Document /></el-icon>
                <span>智能派单</span>
              </el-menu-item>
            </el-menu-item-group>

            <el-menu-item-group title="算法中台支撑">
              <el-menu-item index="/data">
                <el-icon><FolderOpened /></el-icon>
                <span>数据管理</span>
              </el-menu-item>
              <el-menu-item index="/train">
                <el-icon><Cpu /></el-icon>
                <span>算法训练平台</span>
              </el-menu-item>
              <el-menu-item index="/test">
                <el-icon><Odometer /></el-icon>
                <span>测试验证平台</span>
              </el-menu-item>
              <el-menu-item index="/models">
                <el-icon><Files /></el-icon>
                <span>模型管理</span>
              </el-menu-item>
              <el-menu-item index="/results">
                <el-icon><TrendCharts /></el-icon>
                <span>结果分析</span>
              </el-menu-item>
            </el-menu-item-group>

            <el-menu-item-group title="系统管理">
              <el-menu-item index="/shares">
                <el-icon><Connection /></el-icon>
                <span>资源共享</span>
              </el-menu-item>
            </el-menu-item-group>
          </el-menu>
        </el-scrollbar>
      </aside>

      <main class="main-content">
        <header class="top-header">
          <div class="header-left">
            <h3>多园区储能柜健康监测与减碳管理平台</h3>
          </div>
          <div class="header-right">
            <el-tooltip content="点击查看异常电芯工单" placement="bottom">
              <el-badge :value="alarmCount" :max="99" class="alarm-badge" :type="badgeType">
                <el-icon :size="24" @click="goToWorkOrder"><Bell /></el-icon>
              </el-badge>
            </el-tooltip>
            
            <el-dropdown @command="handleCommand" trigger="click">
              <div class="user-info">
                <el-avatar :size="32" src="https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png" />
                <span class="username">{{ currentUsername }}</span>
                <el-icon class="el-icon--right" style="color: #e0e0e0;"><CaretBottom /></el-icon>
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item disabled>角色：{{ currentUserRole }}</el-dropdown-item>
                  <el-dropdown-item divided command="logout" style="color: #f56c6c;">退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </header>

        <div class="page-view">
          <router-view />
        </div>
      </main>
    </div>
  </el-config-provider>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { 
  DataBoard, Monitor, PieChart, Document, Bell, 
  FolderOpened, Cpu, Odometer, Files, TrendCharts, Connection, Setting, CaretBottom
} from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();

const isAuthPage = computed(() => ['/login', '/register'].includes(route.path));
const activeMenu = computed(() => route.path);

const currentUsername = ref('未登录');
const currentUserRole = ref('未知');
const alarmCount = ref(15); 
const highestAlarmLevel = ref('danger'); 
const badgeType = computed(() => highestAlarmLevel.value);

// 提取出一个专门更新用户信息的函数
const updateUserInfo = () => {
  const userStr = localStorage.getItem('userInfo');
  if (userStr) {
    try {
      const user = JSON.parse(userStr);
      currentUsername.value = user.username || 'User';
      currentUserRole.value = user.role === 'admin' ? '系统管理员' : '普通用户';
    } catch (e) {
      console.error('解析用户信息失败', e);
    }
  } else {
    currentUsername.value = '未登录';
    currentUserRole.value = '未知';
  }
};

// 页面初次加载时读取
onMounted(() => {
  updateUserInfo();
});

// 🌟 核心修复：监听路由变化。只要发生页面跳转（比如从登录页跳到系统），立刻刷新右上角头像！
watch(() => route.path, () => {
  updateUserInfo();
});

const goToWorkOrder = () => {
  router.push('/work-order');
};

const handleCommand = (command) => {
  if (command === 'logout') {
    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('userInfo');
    
    ElMessage.success('已安全退出登录');
    router.push('/login');
  }
};
</script>

<style>
body, html { 
  margin: 0; 
  padding: 0; 
  height: 100%; 
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif; 
}
#app { height: 100%; }

/* 登录页全屏容器 */
.auth-layout {
  width: 100vw;
  height: 100vh;
}

/* 仅在进入系统后才应用深色背景和白字 */
.app-container {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background-color: #0b0f19;
  color: #fff; 
}

.sidebar {
  width: 240px;
  background-color: #1e1e2d;
  display: flex;
  flex-direction: column;
}

.logo-box {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid #2b2b3f;
  flex-shrink: 0;
}

.sys-title {
  color: #fff;
  font-size: 18px;
  margin: 0;
}

.el-menu-vertical {
  border-right: none;
}
:deep(.el-menu-item-group__title) {
  color: #6c6d7f !important;
  font-size: 12px;
  padding-left: 20px !important;
  margin-top: 10px;
}
.el-menu-item.is-active {
  background-color: #2b2b3f !important;
  border-left: 4px solid #409eff;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.top-header {
  height: 60px;
  background-color: #151a26;
  border-bottom: 1px solid #232a3b;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 30px;
  flex-shrink: 0;
}

.header-left h3 { margin: 0; color: #e0e0e0; font-weight: 500;}

.header-right {
  display: flex;
  align-items: center;
  gap: 30px;
}

.alarm-badge {
  cursor: pointer;
  animation: pulse 2s infinite;
}
.alarm-badge .el-icon { color: #fff; }

@keyframes pulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.15); }
  100% { transform: scale(1); }
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.3s;
}

.user-info:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.username { color: #e0e0e0; font-size: 14px; }

.page-view {
  flex: 1;
  overflow-y: auto; 
  overflow-x: hidden; 
  background-color: #0b0f19;
  min-height: 0; 
}
</style>