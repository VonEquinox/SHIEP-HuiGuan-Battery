<template>
  <div class="model-management">
    <el-card class="card-container">
      <template #header>
        <div class="card-header">
          <span>模型管理</span>
        </div>
      </template>
      
      <!-- 操作按钮区域 -->
      <div class="operations">
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          创建新模型
        </el-button>
        <el-button type="success" @click="refreshList">
          <el-icon><Refresh /></el-icon>
          刷新列表
        </el-button>
        <el-button type="danger" :disabled="!multipleSelection.length" @click="batchDelete">
          <el-icon><Delete /></el-icon>
          批量删除
        </el-button>
      </div>
      
      <!-- 模型列表 -->
      <el-table
        ref="modelTableRef"
        :data="paginatedModelList"
        stripe
        style="width: 100%"
        @selection-change="handleSelectionChange"
        v-loading="loading"
        empty-text="暂无模型数据"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column type="index" label="序号" width="80" :index="index => (currentPage - 1) * pageSize + index + 1" />
        <el-table-column prop="name" label="模型名称" width="200">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 5px;">
              <el-link type="primary" @click="viewModel(row)">{{ row.name }}</el-link>
              <el-tag 
                v-if="row.is_shared && !row.is_owner" 
                type="success" 
                size="small"
                effect="plain"
              >
                共享
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="algorithm" label="算法类型" width="150">
          <template #default="{ row }">
            <el-tag 
              :type="getAlgorithmTagType(row.algorithm)" 
              size="small"
            >
              {{ getAlgorithmLabel(row.algorithm) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.version }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag 
              :type="getStatusTagType(row.status)" 
              size="small"
            >
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="accuracy" label="准确率" width="120">
          <template #default="{ row }">
            <el-progress 
              :percentage="row.accuracy * 100" 
              :color="getAccuracyColor(row.accuracy)"
              :show-text="false"
              :stroke-width="10"
            />
            <span>{{ (row.accuracy * 100).toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="createdTime" label="创建时间" width="180" />
        <el-table-column prop="updatedTime" label="更新时间" width="180" />
        <el-table-column label="操作" fixed="right" width="450">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 5px;">
              <el-button size="small" @click="loadModel(row)">加载</el-button>
              <el-button size="small" type="primary" @click="downloadModel(row)">下载</el-button>
              <el-button 
                v-if="row.is_owner" 
                size="small" 
                type="success" 
                @click="shareModel(row)"
              >
                分享
              </el-button>
              <el-button 
                v-if="row.is_owner" 
                size="small" 
                type="danger" 
                @click="deleteModel(row)"
              >
                删除
              </el-button>
              <!-- 显示分享信息（被分享给我的模型） -->
              <el-tag 
                v-if="row.is_shared && !row.is_owner && row.share_info" 
                type="success" 
                size="small" 
                effect="plain"
                style="min-width: 100px; text-align: center;"
              >
                分享者: {{ row.share_info.owner_username }}
              </el-tag>
              <el-tag 
                v-if="row.is_shared && !row.is_owner && row.share_info && row.share_info.permission" 
                :type="row.share_info.permission === 'write' ? 'success' : 'info'" 
                size="small" 
                effect="plain"
              >
                {{ row.share_info.permission === 'write' ? '读写' : '只读' }}
              </el-tag>
              <!-- 自己分享出去的模型显示"已共享"标签 -->
              <el-tag 
                v-if="row.is_shared && row.is_owner" 
                type="info" 
                size="small"
              >
                已共享
              </el-tag>
            </div>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :background="true"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
    
    <!-- 创建模型对话框 -->
    <el-dialog
      v-model="createDialogVisible"
      title="创建新模型"
      width="600px"
      :before-close="handleClose"
    >
      <el-form :model="createForm" :rules="createRules" ref="createFormRef" label-width="120px">
        <el-form-item label="模型名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入模型名称" />
        </el-form-item>
        <el-form-item label="算法类型" prop="algorithm">
          <el-select v-model="createForm.algorithm" placeholder="请选择算法类型" style="width: 100%">
            <el-option label="Baseline（传统机器学习）" value="baseline"></el-option>
            <el-option label="BiLSTM（双向长短期记忆网络）" value="bilstm"></el-option>
            <el-option label="DeepHPM（深度物理信息神经网络）" value="deepphm"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="版本号" prop="version">
          <el-input v-model="createForm.version" placeholder="请输入版本号，如：v1.0.0" />
        </el-form-item>
        <el-form-item label="描述信息">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="4"
            placeholder="请输入模型描述信息"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmCreate">确认</el-button>
        </span>
      </template>
    </el-dialog>
    
    <!-- 模型详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="模型详情"
      width="800px"
      :before-close="handleClose"
    >
      <el-descriptions :column="2" border>
        <el-descriptions-item label="模型ID">{{ currentModel.id }}</el-descriptions-item>
        <el-descriptions-item label="模型名称">{{ currentModel.name }}</el-descriptions-item>
        <el-descriptions-item label="算法类型">
          <el-tag :type="getAlgorithmTagType(currentModel.algorithm)">
            {{ getAlgorithmLabel(currentModel.algorithm) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="版本">{{ currentModel.version }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusTagType(currentModel.status)">
            {{ getStatusLabel(currentModel.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="准确率">{{ formatAccuracy(currentModel.accuracy) }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ currentModel.createdTime }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ currentModel.updatedTime }}</el-descriptions-item>
        <el-descriptions-item label="描述信息" :span="2">
          {{ currentModel.description || '暂无描述信息' }}
        </el-descriptions-item>
      </el-descriptions>
      
      <!-- 模型参数信息 -->
      <template v-if="currentModel.params && currentModel.params.length > 0">
        <el-divider content-position="left">模型参数</el-divider>
        <el-table :data="currentModel.params" style="width: 100%" size="small">
          <el-table-column prop="name" label="参数名称" />
          <el-table-column prop="value" label="参数值" />
          <el-table-column prop="description" label="说明" />
        </el-table>
      </template>
      
      <!-- 性能指标 -->
      <el-divider content-position="left">性能指标</el-divider>
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="metric-item">
            <div class="metric-value">{{ currentModel.metrics.rmspe }}</div>
            <div class="metric-label">RMSPE</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item">
            <div class="metric-value">{{ currentModel.metrics.mse }}</div>
            <div class="metric-label">MSE</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item">
            <div class="metric-value">{{ currentModel.metrics.r2 }}</div>
            <div class="metric-label">R²</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item">
            <div class="metric-value">{{ currentModel.metrics.mae }}</div>
            <div class="metric-label">MAE</div>
          </div>
        </el-col>
      </el-row>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="detailDialogVisible = false">关闭</el-button>
          <el-button type="primary" @click="loadModel(currentModel)">加载此模型</el-button>
        </span>
      </template>
    </el-dialog>
    
    <!-- 训练日志对话框 -->
    <el-dialog
      v-model="logDialogVisible"
      title="训练日志"
      width="900px"
      top="5vh"
    >
      <div class="log-content">
        <el-timeline>
          <el-timeline-item
            v-for="(log, index) in currentModel.logs"
            :key="index"
            :timestamp="log.timestamp"
            :color="log.type === 'info' ? '#409EFF' : log.type === 'warning' ? '#E6A23C' : '#F56C6C'"
          >
            <div class="log-item">
              <span class="log-type" :class="`log-${log.type}`">{{ log.type.toUpperCase() }}</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
      <template #footer>
        <el-button @click="logDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed } from 'vue'
import { Plus, Refresh, Delete, User } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getModels, deleteModel as deleteModelAPI, createShare, getUsers } from '@/api'
import request from '@/utils/request'
import { useRouter } from 'vue-router'

export default {
  name: 'ModelManagement',
  setup() {
    const router = useRouter()
    // 模拟模型数据
    const mockModelData = [
      {
        id: 1,
        name: 'Baseline_20231201',
        algorithm: 'baseline',
        version: 'v1.0.1',
        status: 'active',
        accuracy: 0.9567,
        createdTime: '2023-12-01 10:30:00',
        updatedTime: '2023-12-01 10:30:00',
        description: '基础线性回归模型，用于基准比较',
        params: [
          { name: 'layers', value: 1, description: '网络层数' },
          { name: 'nodes', value: 32, description: '每层节点数' },
          { name: 'activation', value: 'relu', description: '激活函数' },
          { name: 'learning_rate', value: 0.01, description: '学习率' },
          { name: 'batch_size', value: 16, description: '批大小' },
          { name: 'epochs', value: 100, description: '训练轮数' }
        ],
        metrics: {
          rmspe: '0.0234',
          mse: '0.0006',
          r2: '0.9567',
          mae: '0.0187'
        },
        logs: [
          { timestamp: '2023-12-01 10:00:00', message: '开始训练 Baseline 模型', type: 'info' },
          { timestamp: '2023-12-01 10:05:23', message: '数据预处理完成，共加载3个电芯数据', type: 'info' },
          { timestamp: '2023-12-01 10:06:15', message: '模型初始化完成，参数量: 0.8M', type: 'info' },
          { timestamp: '2023-12-01 10:07:30', message: '第1轮训练完成，训练损失: 0.0456', type: 'info' },
          { timestamp: '2023-12-01 10:45:10', message: '训练完成，最佳验证损失: 0.0008', type: 'info' }
        ]
      },
      {
        id: 2,
        name: 'BiLSTM_20231202',
        algorithm: 'bilstm',
        version: 'v1.1.2',
        status: 'active',
        accuracy: 0.9789,
        createdTime: '2023-12-02 14:30:00',
        updatedTime: '2023-12-02 14:30:00',
        description: '双向长短期记忆网络，用于序列预测',
        params: [
          { name: 'bidirectional', value: true, description: '是否双向' },
          { name: 'learning_rate', value: 0.001, description: '学习率' },
          { name: 'batch_size', value: 64, description: '批大小' },
          { name: 'epochs', value: 200, description: '训练轮数' }
        ],
        metrics: {
          rmspe: '0.0218',
          mse: '0.0005',
          r2: '0.9723',
          mae: '0.0152'
        },
        logs: [
          { timestamp: '2023-12-02 14:00:00', message: '开始训练 BiLSTM 模型', type: 'info' },
          { timestamp: '2023-12-02 14:05:23', message: '数据预处理完成，共加载5个电芯数据', type: 'info' },
          { timestamp: '2023-12-02 14:06:15', message: 'LSTM模型初始化完成，参数量: 4.2M', type: 'info' },
          { timestamp: '2023-12-02 14:07:30', message: '第1轮训练完成，训练损失: 0.0321', type: 'info' },
          { timestamp: '2023-12-02 16:45:10', message: '训练完成，最佳验证损失: 0.0008', type: 'info' }
        ]
      },
      {
        id: 3,
        name: 'DeepHPM_20231203',
        algorithm: 'deepphm',
        version: 'v2.0.1',
        status: 'inactive',
        accuracy: 0.9786,
        createdTime: '2023-12-03 09:15:00',
        updatedTime: '2023-12-03 09:15:00',
        description: '深度物理信息神经网络，融合电池物理模型',
        params: [
          { name: 'surrogate_layers', value: 4, description: '代理网络层数' },
          { name: 'dynamical_layers', value: 2, description: '动态网络层数' },
          { name: 'nodes', value: 256, description: '每层节点数' },
          { name: 'learning_rate', value: 0.0005, description: '学习率' },
          { name: 'batch_size', value: 32, description: '批大小' },
          { name: 'epochs', value: 300, description: '训练轮数' }
        ],
        metrics: {
          rmspe: '0.0156',
          mse: '0.0003',
          r2: '0.9876',
          mae: '0.0123'
        },
        logs: [
          { timestamp: '2023-12-03 09:00:00', message: '开始训练 DeepHPM 模型', type: 'info' },
          { timestamp: '2023-12-03 09:05:23', message: '数据预处理完成，共加载4个电芯数据', type: 'info' },
          { timestamp: '2023-12-03 09:06:15', message: '物理约束网络初始化完成，参数量: 6.8M', type: 'info' },
          { timestamp: '2023-12-03 09:07:30', message: '第1轮训练完成，训练损失: 0.0256', type: 'info' },
          { timestamp: '2023-12-03 14:20:10', message: '训练完成，最佳验证损失: 0.0005', type: 'info' }
        ]
      },
      {
        id: 4,
        name: 'Baseline_20231115',
        algorithm: 'baseline',
        version: 'v0.9.0',
        status: 'archived',
        accuracy: 0.8945,
        createdTime: '2023-11-15 16:45:00',
        updatedTime: '2023-11-15 16:45:00',
        description: '早期Baseline模型，准确率较低',
        params: [
          { name: 'layers', value: 1, description: '网络层数' },
          { name: 'nodes', value: 32, description: '每层节点数' },
          { name: 'activation', value: 'relu', description: '激活函数' },
          { name: 'learning_rate', value: 0.01, description: '学习率' },
          { name: 'batch_size', value: 16, description: '批大小' },
          { name: 'epochs', value: 50, description: '训练轮数' }
        ],
        metrics: {
          rmspe: '0.0456',
          mse: '0.0012',
          r2: '0.9123',
          mae: '0.0256'
        },
        logs: [
          { timestamp: '2023-11-15 16:00:00', message: '开始训练 Baseline 模型', type: 'info' },
          { timestamp: '2023-11-15 16:05:23', message: '数据预处理完成，共加载2个电芯数据', type: 'info' },
          { timestamp: '2023-11-15 16:06:15', message: '模型初始化完成，参数量: 1.2M', type: 'info' },
          { timestamp: '2023-11-15 16:07:30', message: '第1轮训练完成，训练损失: 0.0678', type: 'info' },
          { timestamp: '2023-11-15 16:45:10', message: '训练完成，最佳验证损失: 0.0015', type: 'info' }
        ]
      }
    ];
    
    // 模型列表数据
    const modelList = ref(mockModelData);
    
    // 从 API 加载模型列表
    const loadModels = async () => {
      loading.value = true;
      
      try {
        const response = await getModels();
        console.log('API返回数据:', response.data);
        
        if (response.data && Array.isArray(response.data)) {
          modelList.value = response.data.map(model => ({
            ...model,
            status: model.is_active ? 'active' : 'inactive'
          }));
          console.log('加载模型数量:', modelList.value.length);
        } else {
          console.error('API返回数据格式错误');
          modelList.value = [];
        }
      } catch (error) {
        console.error('加载模型列表失败:', error);
        modelList.value = [];
      } finally {
        loading.value = false;
      }
    };
    
    // 分页数据
    const currentPage = ref(1)
    const pageSize = ref(10)
    
    // 分页后的数据和总数
    const paginatedModelList = computed(() => {
      const start = (currentPage.value - 1) * pageSize.value
      const end = start + pageSize.value
      return modelList.value.slice(start, end)
    })
    
    const total = computed(() => modelList.value.length)
    
    // 选择的数据
    const multipleSelection = ref([])
    
    // 表格 ref
    const modelTableRef = ref(null)
    
    // 加载状态
    const loading = ref(false)
    
    // 对话框控制
    const createDialogVisible = ref(false)
    const detailDialogVisible = ref(false)
    const logDialogVisible = ref(false)
    
    // 当前模型
    const currentModel = ref({})
    
    // 创建表单
    const createForm = reactive({
      name: '',
      algorithm: '',
      version: 'v1.0.0',
      description: ''
    })
    
    // 创建规则
    const createRules = {
      name: [
        { required: true, message: '请输入模型名称', trigger: 'blur' },
        { min: 3, max: 50, message: '长度在 3 到 50 个字符', trigger: 'blur' }
      ],
      algorithm: [
        { required: true, message: '请选择算法类型', trigger: 'change' }
      ],
      version: [
        { required: true, message: '请输入版本号', trigger: 'blur' }
      ]
    }
    
    // 算法类型标签
    const getAlgorithmTagType = (algorithm) => {
      switch (algorithm) {
        case 'baseline': return 'info'
        case 'bilstm': return 'success'
        case 'deepphm': return 'warning'
        default: return 'info'
      }
    }
    
    // 算法类型标签文本
    const getAlgorithmLabel = (algorithm) => {
      const labels = {
        baseline: 'Baseline',
        bilstm: 'BiLSTM',
        deepphm: 'DeepHPM'
      }
      return labels[algorithm] || algorithm
    }
    
    // 状态标签
    const getStatusTagType = (status) => {
      switch (status) {
        case 'active': return 'success'
        case 'inactive': return 'info'
        case 'archived': return 'warning'
        case 'failed': return 'danger'
        default: return 'info'
      }
    }
    
    // 状态标签文本
    const getStatusLabel = (status) => {
      const labels = {
        active: '活跃',
        inactive: '非活跃',
        archived: '已归档',
        failed: '失败'
      }
      return labels[status] || status
    }
    
    // 准确率颜色
    const getAccuracyColor = (accuracy) => {
      if (accuracy >= 0.95) return '#67C23A'
      if (accuracy >= 0.90) return '#E6A23C'
      return '#F56C6C'
    }
    
    // 表格选择
    const handleSelectionChange = (val) => {
      multipleSelection.value = val
    }
    
    // 分页处理（前端分页，不需要重新加载数据）
    const handleSizeChange = (size) => {
      pageSize.value = size
      currentPage.value = 1
      // 清除选中项
      if (modelTableRef.value) {
        modelTableRef.value.clearSelection()
      }
    }
    
    const handleCurrentChange = (page) => {
      currentPage.value = page
      // 清除选中项
      if (modelTableRef.value) {
        modelTableRef.value.clearSelection()
      }
    }
    
    // 刷新列表
    const refreshList = () => {
      loadModels()
    }
    
    // 打开创建对话框
    const openCreateDialog = () => {
      createDialogVisible.value = true
      // 清除选中项
      if (modelTableRef.value) {
        modelTableRef.value.clearSelection()
      }
    }
    
    // 关闭对话框
    const handleClose = (done) => {
      done()
    }
    
    // 确认创建
    const confirmCreate = () => {
      // 这里应该调用API创建模型
      console.log('创建模型:', createForm)
      createDialogVisible.value = false
      // 重置表单
      Object.assign(createForm, {
        name: '',
        algorithm: '',
        version: 'v1.0.0',
        description: ''
      })
      // 模拟刷新列表
      refreshList()
    }
    
    // 查看模型详情
    const viewModel = async (row) => {
      try {
        // 从后端获取完整的模型信息，包括训练记录
        const response = await getModels()
        console.log('获取模型详情:', response.data)
        
        // 处理不同的数据结构
        let modelsList = []
        if (Array.isArray(response.data)) {
          modelsList = response.data
        } else if (response.data && Array.isArray(response.data.data)) {
          modelsList = response.data.data
        } else {
          console.warn('未知的数据结构:', response.data)
          // 使用原始数据
          currentModel.value = {
            ...row,
            params: row.params || [],
            metrics: row.metrics || { rmspe: '-', mse: '-', r2: '-', mae: '-' }
          }
          detailDialogVisible.value = true
          return
        }
        
        // 查找当前模型
        const modelData = modelsList.find(m => m.id === row.id)
        if (!modelData) {
          console.warn('未找到模型数据')
          currentModel.value = {
            ...row,
            params: row.params || [],
            metrics: row.metrics || { rmspe: '-', mse: '-', r2: '-', mae: '-' }
          }
          detailDialogVisible.value = true
          return
        }
        
        console.log('模型数据详情:', modelData)
        console.log('network_params:', modelData.network_params)
        console.log('training_config:', modelData.training_config)
        console.log('validation_metrics:', modelData.validation_metrics)
        console.log('train_metrics:', modelData.train_metrics)
        
        // 解析训练配置（网络参数）
        let params = []
        
        // 优先使用 network_params，如果没有则使用 training_config
        let paramsSource = modelData.network_params || modelData.training_config
        
        if (paramsSource) {
          try {
            const networkParams = typeof paramsSource === 'string' 
              ? JSON.parse(paramsSource) 
              : paramsSource
            
            // 如果是 training_config，可能需要提取 network_params 子对象
            const actualParams = networkParams.network_params || networkParams
            
            // 将参数转换为表格数据
            if (typeof actualParams === 'object' && actualParams !== null) {
              params = Object.entries(actualParams).map(([key, value]) => ({
                name: key,
                value: String(value),
                description: getParamDescription(key)
              }))
            }
          } catch (e) {
            console.error('解析网络参数失败:', e, paramsSource)
          }
        }
        
        // 解析性能指标
        let metrics = {
          rmspe: '-',
          mse: '-',
          r2: '-',
          mae: '-'
        }
        
        // 优先使用验证集指标，其次是训练集指标
        const metricsData = modelData.validation_metrics || modelData.train_metrics
        if (metricsData) {
          try {
            const parsedMetrics = typeof metricsData === 'string' 
              ? JSON.parse(metricsData) 
              : metricsData
            
            metrics = {
              rmspe: parsedMetrics.rmspe ? parsedMetrics.rmspe.toFixed(6) : '-',
              mse: parsedMetrics.mse ? parsedMetrics.mse.toFixed(8) : '-',
              r2: parsedMetrics.r2 ? parsedMetrics.r2.toFixed(4) : '-',
              mae: parsedMetrics.mae ? parsedMetrics.mae.toFixed(6) : '-'
            }
          } catch (e) {
            console.error('解析性能指标失败:', e)
          }
        }
        
        // 设置当前模型数据
        currentModel.value = {
          ...row,
          params,
          metrics,
          accuracy: metrics.r2 !== '-' ? parseFloat(metrics.r2) : row.accuracy
        }
        
        console.log('处理后的模型数据:', currentModel.value)
        detailDialogVisible.value = true
      } catch (error) {
        console.error('获取模型详情失败:', error)
        // 失败时使用原始数据
        currentModel.value = {
          ...row,
          params: row.params || [],
          metrics: row.metrics || { rmspe: '-', mse: '-', r2: '-', mae: '-' }
        }
        detailDialogVisible.value = true
      }
    }
    
    // 获取参数说明
    const getParamDescription = (paramName) => {
      const descriptions = {
        hidden_size: '隐藏层大小',
        num_layers: '网络层数',
        learning_rate: '学习率',
        batch_size: '批次大小',
        num_epochs: '训练轮次',
        dropout: 'Dropout比例',
        weight_decay: '权重衰减',
        optimizer: '优化器',
        loss_function: '损失函数',
        // 新增更多参数说明
        input_size: '输入维度',
        output_size: '输出维度',
        sequence_length: '序列长度',
        bidirectional: '是否双向',
        activation: '激活函数',
        use_batch_norm: '是否使用BatchNorm'
      }
      return descriptions[paramName] || ''
    }
    
    // 格式化准确率显示
    const formatAccuracy = (accuracy) => {
      if (accuracy === null || accuracy === undefined) {
        return '-'
      }
      // 如果是 R² 值（0-1之间），直接显示
      if (accuracy >= 0 && accuracy <= 1) {
        return accuracy.toFixed(4)
      }
      // 如果是百分比形式，转换为百分比显示
      if (accuracy > 1 || accuracy < -1) {
        return `${accuracy.toFixed(2)}%`
      }
      return accuracy.toFixed(4)
    }
    
    // 加载模型（设置为活跃模型）
    const loadModel = async (row) => {
      try {
        // 调用后端 API 设置模型为活跃状态
        const response = await request.post(`/models/${row.id}/activate`)
        
        if (response.data.success) {
          ElMessage.success(`模型 "${row.name}" 已加载并设置为活跃模型`)
          // 刷新列表
          await loadModels()
        } else {
          ElMessage.error(response.data.message || '加载模型失败')
        }
      } catch (error) {
        console.error('加载模型失败:', error)
        ElMessage.error('加载模型失败: ' + (error.response?.data?.message || error.message))
      }
    }
    
    // 下载模型
    const downloadModel = async (row) => {
      try {
        ElMessage.info(`正在准备下载模型: ${row.name}`)
        
        console.log('下载模型 ID:', row.id)
        console.log('请求 URL:', `/models/${row.id}/download`)
        
        // 使用 Blob 方式下载文件
        const response = await request.get(`/models/${row.id}/download`, {
          responseType: 'blob'
        })
        
        console.log('响应数据:', response)
        
        // 创建下载链接
        const url = window.URL.createObjectURL(new Blob([response.data]))
        const link = document.createElement('a')
        link.href = url
        
        // 设置文件名
        const filename = `${row.name}.pth`
        link.setAttribute('download', filename)
        
        // 触发下载
        document.body.appendChild(link)
        link.click()
        
        // 清理
        link.remove()
        window.URL.revokeObjectURL(url)
        
        ElMessage.success(`模型 "${row.name}" 下载成功`)
      } catch (error) {
        console.error('下载模型失败:', error)
        console.error('错误详情:', error.response)
        
        // 显示更详细的错误信息
        let errorMsg = '下载模型失败'
        if (error.response?.status === 404) {
          const detail = error.response?.data?.detail || ''
          if (detail.includes('无权') || detail.includes('权限')) {
            errorMsg = '无权下载此模型（可能是权限问题）'
          } else if (detail.includes('文件不存在') || detail.includes('未配置')) {
            errorMsg = '模型文件不存在：该模型的训练文件可能已被删除或路径配置错误，请联系模型所有者或管理员'
          } else {
            errorMsg = '模型文件不存在或路由未找到，请确保后端已重启'
          }
        } else if (error.response?.status === 403) {
          errorMsg = '无权下载此模型（权限不足）'
        } else if (error.response?.status === 401) {
          errorMsg = '未登录或登录已过期'
        } else if (error.response?.data?.detail) {
          errorMsg = error.response.data.detail
        } else if (error.response?.data?.message) {
          errorMsg = error.response.data.message
        }
        
        ElMessage.error(errorMsg)
      }
    }
    
    // 删除模型
    const deleteModel = async (row) => {
      try {
        await ElMessageBox.confirm(
          `确定要删除模型 "${row.name}" 吗？此操作不可恢复！`,
          '警告',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning'
          }
        )
        
        console.log('删除模型 ID:', row.id, '名称:', row.name)
        
        // 调用后端 API 删除模型
        const response = await deleteModelAPI(row.id)
        console.log('删除API响应:', response)
        
        if (response.data.success) {
          ElMessage.success(`模型 "${row.name}" 已删除`)
          // 直接从前端列表移除
          modelList.value = modelList.value.filter(m => m.id !== row.id)
          console.log('删除后剩余模型数:', modelList.value.length)
          
          // 判断当前页是否超出总页数
          const totalPages = Math.ceil(modelList.value.length / pageSize.value)
          if (currentPage.value > totalPages && totalPages > 0) {
            currentPage.value = totalPages
          }
        } else {
          ElMessage.error(response.data.message || '删除模型失败')
        }
      } catch (error) {
        if (error !== 'cancel') {
          console.error('删除模型失败:', error)
          ElMessage.error('删除模型失败: ' + (error.response?.data?.message || error.message))
        }
      }
    }
    
    // 分享模型
    const shareModel = async (row) => {
      try {
        // 跳转到资源共享管理页面，并传递模型信息
        router.push({
          path: '/shares',
          query: {
            action: 'share',
            resource_type: 'model',
            resource_id: row.id
          }
        })
      } catch (error) {
        console.error('跳转失败:', error)
      }
    }
    
    // 批量删除
    const batchDelete = async () => {
      if (!multipleSelection.value.length) {
        ElMessage.warning('请先选择要删除的模型')
        return
      }
      
      try {
        await ElMessageBox.confirm(
          `确定要删除选中的 ${multipleSelection.value.length} 个模型吗？此操作不可恢复！`,
          '警告',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning'
          }
        )
        
        // 批量删除
        const deletePromises = multipleSelection.value.map(model => deleteModelAPI(model.id))
        await Promise.all(deletePromises)
        
        ElMessage.success(`成功删除 ${multipleSelection.value.length} 个模型`)
        // 直接从前端列表移除
        const deleteIds = multipleSelection.value.map(m => m.id)
        modelList.value = modelList.value.filter(m => !deleteIds.includes(m.id))
        console.log('批量删除后剩余模型数:', modelList.value.length)
        
        // 判断当前页是否超出总页数
        const totalPages = Math.ceil(modelList.value.length / pageSize.value)
        if (currentPage.value > totalPages && totalPages > 0) {
          currentPage.value = totalPages
        }
      } catch (error) {
        if (error !== 'cancel') {
          console.error('批量删除模型失败:', error)
          ElMessage.error('批量删除模型失败: ' + (error.response?.data?.message || error.message))
        }
      }
    }
    
    onMounted(async () => {
      // 尝试从API加载数据，如果失败则使用模拟数据
      await loadModels();
    })
    
    return {
      modelList,
      paginatedModelList,
      currentPage,
      pageSize,
      total,
      multipleSelection,
      modelTableRef,
      loading,
      createDialogVisible,
      detailDialogVisible,
      logDialogVisible,
      currentModel,
      createForm,
      createRules,
      getAlgorithmTagType,
      getAlgorithmLabel,
      getStatusTagType,
      getStatusLabel,
      getAccuracyColor,
      formatAccuracy,
      handleSelectionChange,
      handleSizeChange,
      handleCurrentChange,
      refreshList,
      openCreateDialog,
      handleClose,
      confirmCreate,
      viewModel,
      loadModel,
      downloadModel,
      shareModel,
      deleteModel,
      batchDelete
    }
  }
}
</script>

<style scoped>
.model-management {
  padding: 20px;
}

.card-container {
  min-height: 600px;
}

.operations {
  margin-bottom: 20px;
}

.pagination {
  margin-top: 20px;
  text-align: center;
}

.metric-item {
  text-align: center;
  padding: 20px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background-color: #fafafa;
}

.metric-value {
  font-size: 24px;
  font-weight: bold;
  color: #409eff;
  margin-bottom: 5px;
}

.metric-label {
  font-size: 14px;
  color: #606266;
}

.log-content {
  max-height: 60vh;
  overflow-y: auto;
}

.log-item {
  display: flex;
  align-items: center;
}

.log-type {
  font-weight: bold;
  margin-right: 10px;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
}

.log-info {
  background-color: #ecf5ff;
  color: #409eff;
}

.log-warning {
  background-color: #fdf6ec;
  color: #e6a23c;
}

.log-error {
  background-color: #fef0f0;
  color: #f56c6c;
}

.log-message {
  flex: 1;
}
</style>