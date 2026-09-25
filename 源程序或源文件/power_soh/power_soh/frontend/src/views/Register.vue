<template>
  <div class="register-container">
    <!-- 背景动画元素 -->
    <div class="bg-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
      <div class="shape shape-4"></div>
    </div>
    
    <div class="register-content">
      <!-- 左侧品牌区 -->
      <div class="brand-section">
        <div class="brand-icon">
          <el-icon :size="80" color="#fff"><Cpu /></el-icon>
        </div>
        <h1 class="brand-title">储能电池寿命预测系统</h1>
        <p class="brand-desc">
          加入我们，体验智能电池健康管理的全新方式
        </p>
        <div class="feature-list">
          <div class="feature-item">
            <el-icon><Histogram /></el-icon>
            <span>专业数据分析</span>
          </div>
          <div class="feature-item">
            <el-icon><Aim /></el-icon>
            <span>精准寿命预测</span>
          </div>
          <div class="feature-item">
            <el-icon><Setting /></el-icon>
            <span>智能维护建议</span>
          </div>
        </div>
      </div>
      
      <!-- 右侧注册表单 -->
      <div class="register-card-wrapper">
        <el-card class="register-card" shadow="always">
          <div class="card-header">
            <div class="avatar-icon">
              <el-icon :size="40" color="#67C23A"><UserFilled /></el-icon>
            </div>
            <h2>创建账户</h2>
            <p>填写以下信息开始使用</p>
          </div>
          
          <el-form 
            :model="registerForm" 
            :rules="registerRules" 
            ref="registerFormRef"
            label-position="top"
            size="large"
            class="register-form"
          >
            <el-form-item label="用户名" prop="username">
              <el-input 
                v-model="registerForm.username" 
                placeholder="请输入用户名"
                :prefix-icon="User"
                clearable
              />
            </el-form-item>
            
            <el-form-item label="邮箱" prop="email">
              <el-input 
                v-model="registerForm.email" 
                placeholder="请输入邮箱"
                :prefix-icon="Message"
                clearable
              />
            </el-form-item>
            
            <el-form-item label="密码" prop="password">
              <el-input 
                v-model="registerForm.password" 
                type="password" 
                placeholder="请输入密码"
                :prefix-icon="Lock"
                show-password
              />
            </el-form-item>
            
            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input 
                v-model="registerForm.confirmPassword" 
                type="password" 
                placeholder="请再次输入密码"
                :prefix-icon="Lock"
                show-password
                @keyup.enter="handleRegister"
              />
            </el-form-item>
            
            <el-form-item>
              <el-button 
                type="primary" 
                size="large" 
                class="register-btn"
                @click="handleRegister"
                :loading="loading"
              >
                <el-icon v-if="!loading"><Check /></el-icon>
                {{ loading ? '注册中...' : '立即注册' }}
              </el-button>
            </el-form-item>
          </el-form>
          
          <div class="card-footer">
            <span>已有账户？</span>
            <el-link type="primary" @click="handleGoToLogin">
              返回登录
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
  User, Message, Lock, Check, Cpu, Histogram, Aim, Setting, UserFilled 
} from '@element-plus/icons-vue';
import request from '@/utils/request';

export default {
  name: 'Register',
  components: {
    User, Message, Lock, Check, Cpu, Histogram, Aim, Setting, UserFilled
  },
  setup() {
    const router = useRouter();
    const registerFormRef = ref(null);
    const loading = ref(false);
    
    const registerForm = reactive({
      username: '',
      email: '',
      password: '',
      confirmPassword: ''
    });
    
    // 自定义验证规则
    const validateConfirmPassword = (rule, value, callback) => {
      if (value !== registerForm.password) {
        callback(new Error('两次输入的密码不一致'));
      } else {
        callback();
      }
    };
    
    const registerRules = {
      username: [
        { required: true, message: '请输入用户名', trigger: 'blur' },
        { min: 3, max: 20, message: '用户名长度应在3-20个字符之间', trigger: 'blur' }
      ],
      email: [
        { required: true, message: '请输入邮箱', trigger: 'blur' },
        { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
      ],
      password: [
        { required: true, message: '请输入密码', trigger: 'blur' },
        { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
      ],
      confirmPassword: [
        { required: true, message: '请再次输入密码', trigger: 'blur' },
        { validator: validateConfirmPassword, trigger: 'blur' }
      ]
    };
    
    const handleRegister = async () => {
      if (!registerFormRef.value) return;
      
      const valid = await registerFormRef.value.validate().catch(() => false);
      if (!valid) return;
      
      loading.value = true;
      try {
        const response = await request.post('/auth/register', {
          username: registerForm.username,
          email: registerForm.email,
          password: registerForm.password
        });
        
        const data = response.data;
        
        // 后端返回 access_token 表示注册成功
        if (data.access_token) {
          ElMessage.success('注册成功，请登录');
          router.push('/login');
        } else {
          ElMessage.error('注册失败');
        }
      } catch (error) {
        console.error('注册错误:', error);
        const msg = error.response?.data?.detail || '注册失败';
        ElMessage.error(msg);
      } finally {
        loading.value = false;
      }
    };
    
    const handleGoToLogin = () => {
      router.push('/login');
    };
    
    return {
      registerFormRef,
      registerForm,
      registerRules,
      loading,
      handleRegister,
      handleGoToLogin,
      User,
      Message,
      Lock,
      Check,
      Cpu,
      Histogram,
      Aim,
      Setting,
      UserFilled
    };
  }
};
</script>

<style scoped>
.register-container {
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
  background: linear-gradient(45deg, rgba(103, 194, 58, 0.1), rgba(64, 158, 255, 0.1));
  animation: float 15s infinite ease-in-out;
}

.shape-1 {
  width: 400px;
  height: 400px;
  top: -100px;
  right: -100px;
  animation-delay: 0s;
}

.shape-2 {
  width: 300px;
  height: 300px;
  bottom: 10%;
  left: -50px;
  animation-delay: -5s;
}

.shape-3 {
  width: 200px;
  height: 200px;
  top: 40%;
  left: 20%;
  animation-delay: -10s;
}

.shape-4 {
  width: 250px;
  height: 250px;
  bottom: -50px;
  right: 30%;
  animation-delay: -7s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) rotate(0deg);
  }
  25% {
    transform: translate(-30px, 30px) rotate(90deg);
  }
  50% {
    transform: translate(0, 50px) rotate(180deg);
  }
  75% {
    transform: translate(30px, 30px) rotate(270deg);
  }
}

.register-content {
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
  background: linear-gradient(135deg, #67C23A 0%, #409EFF 100%);
  border-radius: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 30px;
  box-shadow: 0 20px 40px rgba(103, 194, 58, 0.3);
  animation: pulse 2s infinite ease-in-out;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 20px 40px rgba(103, 194, 58, 0.3);
  }
  50% {
    transform: scale(1.05);
    box-shadow: 0 25px 50px rgba(103, 194, 58, 0.4);
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

/* 注册卡片 */
.register-card-wrapper {
  flex: 0 0 420px;
}

.register-card {
  border-radius: 20px;
  border: none;
  box-shadow: 0 25px 50px rgba(0, 0, 0, 0.3);
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
}

.register-card :deep(.el-card__body) {
  padding: 40px;
}

.card-header {
  text-align: center;
  margin-bottom: 24px;
}

.avatar-icon {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, #e6f7e6 0%, #c8f7c8 100%);
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

.register-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: #303133;
}

.register-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.register-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 4px 12px rgba(103, 194, 58, 0.15);
}

.register-btn {
  width: 100%;
  height: 50px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 12px;
  background: linear-gradient(135deg, #67C23A 0%, #85ce61 100%);
  border: none;
  transition: all 0.3s ease;
}

.register-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 20px rgba(103, 194, 58, 0.3);
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
  .register-content {
    flex-direction: column;
    gap: 40px;
  }
  
  .brand-section {
    display: none;
  }
  
  .register-card-wrapper {
    flex: none;
    width: 100%;
    max-width: 420px;
  }
}
</style>