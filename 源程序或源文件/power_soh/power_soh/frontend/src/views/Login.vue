<template>
  <div class="login-container">
    <!-- 背景动画元素 -->
    <div class="bg-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
      <div class="shape shape-4"></div>
    </div>
    
    <div class="login-content">
      <!-- 左侧品牌区 -->
      <div class="brand-section">
        <div class="brand-icon">
          <el-icon :size="80" color="#fff"><Cpu /></el-icon>
        </div>
        <h1 class="brand-title">储能电池寿命预测系统</h1>
        <p class="brand-desc">
          基于深度学习的智能电池健康状态评估与寿命预测平台
        </p>
        <div class="feature-list">
          <div class="feature-item">
            <el-icon><DataAnalysis /></el-icon>
            <span>SOH健康状态评估</span>
          </div>
          <div class="feature-item">
            <el-icon><TrendCharts /></el-icon>
            <span>RUL剩余寿命预测</span>
          </div>
          <div class="feature-item">
            <el-icon><Monitor /></el-icon>
            <span>实时数据监控</span>
          </div>
        </div>
      </div>
      
      <!-- 右侧登录表单 -->
      <div class="login-card-wrapper">
        <el-card class="login-card" shadow="always">
          <div class="card-header">
            <div class="avatar-icon">
              <el-icon :size="40" color="#409EFF"><User /></el-icon>
            </div>
            <h2>用户登录</h2>
            <p>欢迎回来，请登录您的账户</p>
          </div>
          
          <el-form 
            :model="loginForm" 
            :rules="loginRules" 
            ref="loginFormRef"
            label-position="top"
            size="large"
            class="login-form"
          >
            <el-form-item label="用户名" prop="username">
              <el-input 
                v-model="loginForm.username" 
                placeholder="请输入用户名"
                :prefix-icon="User"
                clearable
              />
            </el-form-item>
            
            <el-form-item label="密码" prop="password">
              <el-input 
                v-model="loginForm.password" 
                type="password" 
                placeholder="请输入密码"
                :prefix-icon="Lock"
                show-password
                @keyup.enter="handleLogin"
              />
            </el-form-item>
            
            <el-form-item>
              <div class="form-options">
                <el-checkbox v-model="loginForm.rememberMe">记住我</el-checkbox>
                <el-link type="primary" underline="never">忘记密码？</el-link>
              </div>
            </el-form-item>
            
            <el-form-item>
              <el-button 
                type="primary" 
                size="large" 
                class="login-btn"
                @click="handleLogin"
                :loading="loading"
              >
                <el-icon v-if="!loading"><Right /></el-icon>
                {{ loading ? '登录中...' : '登 录' }}
              </el-button>
            </el-form-item>
          </el-form>
          
          <div class="card-footer">
            <span>还没有账户？</span>
            <el-link type="primary" @click="handleGoToRegister">
              立即注册
            </el-link>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { 
  User, Lock, Right, Cpu, DataAnalysis, TrendCharts, Monitor 
} from '@element-plus/icons-vue';
import request from '@/utils/request';

export default {
  name: 'Login',
  components: {
    User, Lock, Right, Cpu, DataAnalysis, TrendCharts, Monitor
  },
  setup() {
    const router = useRouter();
    const loginFormRef = ref(null);
    const loading = ref(false);
    
    const loginForm = reactive({
      username: '',
      password: '',
      rememberMe: false
    });
    
    const loginRules = {
      username: [
        { required: true, message: '请输入用户名', trigger: 'blur' },
        { min: 3, max: 20, message: '用户名长度应在3-20个字符之间', trigger: 'blur' }
      ],
      password: [
        { required: true, message: '请输入密码', trigger: 'blur' },
        { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
      ]
    };
    
    const handleLogin = async () => {
      if (!loginFormRef.value) return;
      
      const valid = await loginFormRef.value.validate().catch(() => false);
      if (!valid) return;
      
      loading.value = true;
      try {
        const response = await request.post('/auth/login', {
          username: loginForm.username,
          password: loginForm.password
        });
        
        const data = response.data;
        
        // 后端返回 access_token 和 user 对象
        if (data.access_token) {
          // 存储token和用户信息
          localStorage.setItem('token', data.access_token);
          if (data.refresh_token) {
            localStorage.setItem('refreshToken', data.refresh_token);
          }
          localStorage.setItem('userInfo', JSON.stringify(data.user));
          
          ElMessage.success('登录成功');
          
          // 等待一下确保 localStorage 已更新，然后跳转
          setTimeout(() => {
            // 跳转到仪表板
            router.replace('/dashboard');
          }, 100);
        } else {
          ElMessage.error('登录失败');
        }
      } catch (error) {
        console.error('登录错误:', error);
        const msg = error.response?.data?.detail || '登录失败，请检查用户名和密码';
        ElMessage.error(msg);
      } finally {
        loading.value = false;
      }
    };
    
    const handleGoToRegister = () => {
      router.push('/register');
    };
    
    return {
      loginFormRef,
      loginForm,
      loginRules,
      loading,
      handleLogin,
      handleGoToRegister,
      User,
      Lock,
      Right,
      Cpu,
      DataAnalysis,
      TrendCharts,
      Monitor
    };
  }
};
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  padding: 20px;
  position: relative;
  overflow: hidden;
}

/* 背景动画形状 */
.bg-shapes {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  z-index: 0;
}

.shape {
  position: absolute;
  border-radius: 50%;
  background: linear-gradient(45deg, rgba(64, 158, 255, 0.1), rgba(103, 194, 58, 0.1));
  animation: float 15s infinite ease-in-out;
}

.shape-1 {
  width: 400px;
  height: 400px;
  top: -100px;
  left: -100px;
  animation-delay: 0s;
}

.shape-2 {
  width: 300px;
  height: 300px;
  top: 50%;
  right: -50px;
  animation-delay: -5s;
}

.shape-3 {
  width: 200px;
  height: 200px;
  bottom: -50px;
  left: 30%;
  animation-delay: -10s;
}

.shape-4 {
  width: 250px;
  height: 250px;
  top: 20%;
  left: 50%;
  animation-delay: -7s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) rotate(0deg);
  }
  25% {
    transform: translate(30px, -30px) rotate(90deg);
  }
  50% {
    transform: translate(0, -50px) rotate(180deg);
  }
  75% {
    transform: translate(-30px, -30px) rotate(270deg);
  }
}

.login-content {
  display: flex;
  gap: 60px;
  align-items: center;
  z-index: 1;
  max-width: 1000px;
  width: 100%;
}

/* 品牌区域 */
.brand-section {
  flex: 1;
  color: #fff;
  text-align: center;
}

.brand-icon {
  width: 120px;
  height: 120px;
  background: linear-gradient(135deg, #409EFF 0%, #67C23A 100%);
  border-radius: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 30px;
  box-shadow: 0 20px 40px rgba(64, 158, 255, 0.3);
  animation: pulse 2s infinite ease-in-out;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 20px 40px rgba(64, 158, 255, 0.3);
  }
  50% {
    transform: scale(1.05);
    box-shadow: 0 25px 50px rgba(64, 158, 255, 0.4);
  }
}

.brand-title {
  font-size: 32px;
  font-weight: 700;
  margin-bottom: 16px;
  background: linear-gradient(90deg, #fff 0%, #a8edea 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.brand-desc {
  font-size: 16px;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 40px;
  line-height: 1.6;
}

.feature-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.feature-item {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 15px;
  color: rgba(255, 255, 255, 0.8);
  padding: 12px 24px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 30px;
  backdrop-filter: blur(10px);
  transition: all 0.3s ease;
}

.feature-item:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: translateX(10px);
}

.feature-item .el-icon {
  font-size: 20px;
  color: #67C23A;
}

/* 登录卡片 */
.login-card-wrapper {
  flex: 0 0 420px;
}

.login-card {
  border-radius: 20px;
  border: none;
  box-shadow: 0 25px 50px rgba(0, 0, 0, 0.3);
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
}

.login-card :deep(.el-card__body) {
  padding: 40px;
}

.card-header {
  text-align: center;
  margin-bottom: 30px;
}

.avatar-icon {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
}

.card-header h2 {
  font-size: 24px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 8px;
}

.card-header p {
  font-size: 14px;
  color: #909399;
}

.login-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: #303133;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.login-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.15);
}

.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.login-btn {
  width: 100%;
  height: 50px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 12px;
  background: linear-gradient(135deg, #409EFF 0%, #66b1ff 100%);
  border: none;
  transition: all 0.3s ease;
}

.login-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 20px rgba(64, 158, 255, 0.3);
}

.card-footer {
  text-align: center;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
  font-size: 14px;
  color: #909399;
}

.card-footer .el-link {
  margin-left: 8px;
  font-weight: 500;
}

/* 响应式设计 */
@media (max-width: 900px) {
  .login-content {
    flex-direction: column;
    gap: 40px;
  }
  
  .brand-section {
    display: none;
  }
  
  .login-card-wrapper {
    flex: none;
    width: 100%;
    max-width: 420px;
  }
}
</style>